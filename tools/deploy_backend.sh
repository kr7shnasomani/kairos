#!/usr/bin/env bash
# Deploy this working tree to the EC2 backend, the way that was proven on the first security rollout.
#
#   make deploy-backend               # asks for confirmation
#   tools/deploy_backend.sh --yes     # no prompt
#   tools/deploy_backend.sh --files   # copy files only (docs, tools, compose): no rebuild, no restart
#
# Steps: backup the server tree and tag the running images, rsync (never touches the server's .env),
# rebuild and restart with `make prod`, restart OPA and Caddy (the two things `make prod` does not
# pick up, see docs/implementation/status.md Known Pitfalls), then verify. Rollback: restore the
# backup directory it prints and re-tag the two `rollback-*` images.
#
# Needs: SSH on port 22 open to your current IP in the security group, and the key at $SSH_KEY.
set -euo pipefail
# shellcheck source=tools/_deploy_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_deploy_common.sh"
cd "$ROOT"

if [ "${1:-}" = "--files" ]; then
  remote true || { echo "cannot reach $SERVER over SSH: open port 22 to your IP first" >&2; exit 2; }
  rsync -az --delete "${RSYNC_EXCLUDES[@]}" -e "ssh ${SSH_OPTS[*]}" ./ "$SERVER:~/kairos/"
  echo "files copied, nothing rebuilt or restarted. If backend code, the Caddyfile or a policy changed, use --yes instead."
  exit 0
fi

if [ "${1:-}" != "--yes" ]; then
  echo "This rebuilds and restarts the live backend ($SERVER). The API is briefly unavailable."
  read -r -p "Type 'deploy' to continue: " ok; [ "$ok" = "deploy" ] || { echo "aborted"; exit 1; }
fi

remote true || { echo "cannot reach $SERVER over SSH: open port 22 to your IP first" >&2; exit 2; }
for k in MOC_WEBHOOK_SECRET CONNECTOR_SHARED_SECRET; do
  remote "grep -q '^$k=' ~/kairos/.env" || { echo "server .env is missing $k: the API or connector would refuse to start" >&2; exit 3; }
done

TS=$(date +%Y%m%d-%H%M%S)
echo "1/6 backup ~/kairos.bak-$TS and tag rollback images"
remote "cp -a ~/kairos ~/kairos.bak-$TS && docker tag kairos-backend:local kairos-backend:rollback-$TS && docker tag kairos-connector:local kairos-connector:rollback-$TS"

echo "2/6 copy the code"
rsync -az --delete "${RSYNC_EXCLUDES[@]}" -e "ssh ${SSH_OPTS[*]}" ./ "$SERVER:~/kairos/"

echo "3/6 validate the compose file with the server's real .env"
remote "cd ~/kairos && docker compose -f docker-compose.yml --profile prod config -q"

echo "4/6 rebuild and restart (make prod)"
remote "cd ~/kairos && make prod > ~/deploy-$TS.log 2>&1" || { echo "make prod failed, log: ~/deploy-$TS.log on the server" >&2; exit 4; }

echo "5/6 restart OPA and Caddy so the new policy and Caddyfile load"
remote "docker restart kairos-opa kairos-caddy >/dev/null"

echo "6/6 verify"
for i in $(seq 1 40); do
  [ "$(remote 'docker inspect -f "{{.State.Health.Status}}" kairos-backend-api 2>/dev/null')" = "healthy" ] && break; sleep 4
done
code=$(curl -s -m 20 -o /dev/null -w '%{http_code}' "$API_URL/health/")
[ "$code" = "200" ] || { echo "API health returned $code. Roll back: see the header of this script, backup ~/kairos.bak-$TS" >&2; exit 5; }
echo "deployed. backup: ~/kairos.bak-$TS  rollback images: rollback-$TS"
echo "next: tools/sync_check.sh --deep"
