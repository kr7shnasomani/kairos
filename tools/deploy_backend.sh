#!/usr/bin/env bash
# Deploy this working tree to the EC2 backend, the way that was proven on the first security rollout.
#
#   make deploy-backend               # asks for confirmation
#   tools/deploy_backend.sh --yes     # no prompt
#   tools/deploy_backend.sh --files   # copy files only (docs, tools, compose): no rebuild, no restart
#
# Steps: backup the server tree (without any .env file) and tag the running images, rsync (never
# touches the server's .env), rebuild and restart with `make prod`, restart OPA and Caddy (the two
# things `make prod` does not pick up, see docs/status.md Known Pitfalls), verify, then prune: only
# the newest $KEEP backups and rollback images stay, and build cache unused for a week goes.
#
# Rollback: re-tag the two `rollback-*` images and restore the backup directory it prints with
#   rsync -a --delete --exclude .env --exclude '.env.bak*' ~/kairos.bak-<TS>/ ~/kairos/
# which keeps the server's current .env. Never move the backup over ~/kairos: it holds no .env.
#
# Needs: the `kairos-ssm` Session Manager alias (docs/DEPLOY.md) and the key at $SSH_KEY, or, without
# the alias, SSH on port 22 open to your current IP in the security group.
set -euo pipefail
# shellcheck source=tools/_deploy_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_deploy_common.sh"
cd "$ROOT"
KEEP=3 # deploy backups and rollback images kept on the server

if [ "${1:-}" = "--files" ]; then
  remote true || { echo "cannot reach $SERVER over SSH: check the kairos-deploy AWS profile (Session Manager), or open port 22 to your IP" >&2; exit 2; }
  rsync -az --delete "${RSYNC_EXCLUDES[@]}" -e "ssh ${SSH_OPTS[*]}" ./ "$SERVER:~/kairos/"
  echo "files copied, nothing rebuilt or restarted. If backend code, the Caddyfile or a policy changed, use --yes instead."
  exit 0
fi

if [ "${1:-}" != "--yes" ]; then
  echo "This rebuilds and restarts the live backend ($SERVER). The API is briefly unavailable."
  echo "After a healthy deploy it permanently deletes all but the newest $KEEP backups and rollback images."
  read -r -p "Type 'deploy' to continue: " ok; [ "$ok" = "deploy" ] || { echo "aborted"; exit 1; }
fi

remote true || { echo "cannot reach $SERVER over SSH: check the kairos-deploy AWS profile (Session Manager), or open port 22 to your IP" >&2; exit 2; }
for k in MOC_WEBHOOK_SECRET CONNECTOR_SHARED_SECRET; do
  remote "grep -q '^$k=' ~/kairos/.env" || { echo "server .env is missing $k: the API or connector would refuse to start" >&2; exit 3; }
done

TS=$(date +%Y%m%d-%H%M%S)
echo "1/7 backup ~/kairos.bak-$TS and tag rollback images"
remote "rsync -a --exclude .env --exclude '.env.bak*' ~/kairos/ ~/kairos.bak-$TS/ && docker tag kairos-backend:local kairos-backend:rollback-$TS && docker tag kairos-connector:local kairos-connector:rollback-$TS"

echo "2/7 copy the code"
rsync -az --delete "${RSYNC_EXCLUDES[@]}" -e "ssh ${SSH_OPTS[*]}" ./ "$SERVER:~/kairos/"

echo "3/7 validate the compose file with the server's real .env"
remote "cd ~/kairos && docker compose -f docker-compose.yml --profile prod config -q"

echo "4/7 rebuild and restart (make prod)"
remote "cd ~/kairos && make prod > ~/deploy-$TS.log 2>&1" || { echo "make prod failed, log: ~/deploy-$TS.log on the server" >&2; exit 4; }

echo "5/7 restart OPA and Caddy so the new policy and Caddyfile load"
remote "docker restart kairos-opa kairos-caddy >/dev/null"

echo "6/7 verify"
for i in $(seq 1 40); do
  [ "$(remote 'docker inspect -f "{{.State.Health.Status}}" kairos-backend-api 2>/dev/null')" = "healthy" ] && break; sleep 4
done
code=$(curl -s -m 20 -o /dev/null -w '%{http_code}' "$API_URL/health/")
[ "$code" = "200" ] || { echo "API health returned $code. Roll back: see the header of this script, backup ~/kairos.bak-$TS" >&2; exit 5; }

# Only after a healthy deploy, so a failed one never removes a rollback point. The [0-9] patterns
# leave hand-named backups and tags (kairos.bak-pre-security) alone.
# shortcut: keeps by age, so $KEEP failed deploys in a row age out the last good backup at the next
# healthy one; mark verified backups if that ever happens.
echo "7/7 prune old backups, rollback images and build cache"
old="tail -n +$((KEEP + 1))"
remote "ls -1d ~/kairos.bak-[0-9]* | sort -r | $old | xargs -r -t rm -rf -- &&
  for repo in kairos-backend kairos-connector; do
    docker images \$repo --format '{{.Repository}}:{{.Tag}}' | grep ':rollback-[0-9]' | sort -r | $old | xargs -r docker rmi || exit 1
  done &&
  docker builder prune -f --filter until=168h" || echo "warning: cleanup failed; the deploy itself succeeded" >&2

echo "deployed. backup: ~/kairos.bak-$TS  rollback images: rollback-$TS"
echo "next: tools/sync_check.sh --deep"
