#!/usr/bin/env bash
# Report drift between this working tree, GitHub, the EC2 backend, Vercel and the local containers.
# Read-only: it never changes anything. Exit status 1 when anything differs.
#
#   make sync-check            # or: tools/sync_check.sh
#   tools/sync_check.sh --deep # also logs in as the demo user on the live API
#
# What "in sync" means here:
#   GitHub    nothing uncommitted, nothing unpushed
#   EC2       a checksum dry run of the deploy rsync finds zero differing files
#   Vercel    the frontend source hash equals the hash recorded at the last `make deploy-frontend`
#   Settings  behaviour flags resolve to the same value locally and on the server; names match
#   Local     every local image is newer than the source it was built from
# Intentional differences (the API address, APP_ENV, secrets) are listed in docs/DEPLOY.md.
set -uo pipefail
# shellcheck source=tools/_deploy_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_deploy_common.sh"
cd "$ROOT"

DEEP=0; [ "${1:-}" = "--deep" ] && DEEP=1
bad=0
row() { printf '  %-30s %-7s %s\n' "$1" "$2" "$3"; [ "$2" = "OK" ] || bad=1; }
section() { printf '\n%s\n' "$1"; }

# Value of KEY in a .env-style stream, else its default from .env.example.
effective() { # $1 key, $2 env text
  local v; v=$(printf '%s\n' "$2" | grep -E "^$1=" | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e "s/^['\"]//" -e "s/['\"]$//")
  [ -n "$v" ] || v=$(grep -E "^$1=" .env.example | head -1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//')
  printf '%s' "$v"
}

section "GitHub"
dirty=$(git status --porcelain | wc -l | tr -d ' ')
ahead=$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo "?")
[ "$dirty" = "0" ] && row "uncommitted changes" OK "none" || row "uncommitted changes" DRIFT "$dirty files differ from HEAD"
[ "$ahead" = "0" ] && row "unpushed commits" OK "none" || row "unpushed commits" DRIFT "$ahead"

section "Backend on EC2"
if remote true 2>/dev/null; then
  changed=$(rsync -azn --checksum --delete --itemize-changes "${RSYNC_EXCLUDES[@]}" -e "ssh ${SSH_OPTS[*]}" ./ "$SERVER:~/kairos/" 2>/dev/null | grep -vE '^\.d|^\.L|^cd' | wc -l | tr -d ' ')
  [ "$changed" = "0" ] && row "code on server" OK "identical to this tree" || row "code on server" DRIFT "$changed files differ (run: make deploy-backend)"
  unhealthy=$(remote 'docker ps --format "{{.Names}} {{.Status}}" | grep -ciE "unhealthy|restarting|exited"' 2>/dev/null)
  up=$(remote 'docker ps -q | wc -l' 2>/dev/null | tr -d ' ')
  [ "${unhealthy:-1}" = "0" ] && row "containers" OK "$up running, none unhealthy" || row "containers" DRIFT "${unhealthy:-?} unhealthy of $up"
else
  row "code on server" UNKNOWN "cannot reach $SERVER over SSH (is port 22 open to your current IP?)"
fi
if remote true 2>/dev/null; then
  for pair in "kairos-opa:infra/policies/kairos.rego" "kairos-caddy:infra/caddy/Caddyfile"; do
    c=${pair%%:*}; f=${pair#*:}
    out=$(remote "s=\$(date -d \"\$(docker inspect -f '{{.State.StartedAt}}' $c)\" +%s); m=\$(stat -c %Y ~/kairos/$f); echo \$s \$m" 2>/dev/null)
    set -- $out
    if [ -n "${1:-}" ] && [ "$1" -ge "${2:-0}" ]; then row "server $c" OK "started after $f last changed"
    else row "server $c" DRIFT "still running an older $f (run: docker restart $c)"; fi
  done
fi
code=$(curl -s -m 20 -o /dev/null -w '%{http_code}' "$API_URL/health/"); [ "$code" = "200" ] && row "live API /health" OK "200" || row "live API /health" DRIFT "$code"

section "Frontend on Vercel"
now=$(frontend_hash); rec=$(cat .vercel/deployed-frontend.sha 2>/dev/null || echo "")
if [ -z "$rec" ]; then row "source vs last deploy" UNKNOWN "no record yet (run: make deploy-frontend)"
elif [ "$now" = "$rec" ]; then row "source vs last deploy" OK "hash $now"
else row "source vs last deploy" DRIFT "local $now, deployed $rec (run: make deploy-frontend)"; fi
curl -s -m 20 "$WEB_URL/login" | grep -q "Explore the live demo" && row "demo button on live login" OK "present" || row "demo button on live login" DRIFT "missing"
if command -v vercel >/dev/null 2>&1; then
  names=$(vercel env ls production --scope "$VERCEL_SCOPE" 2>/dev/null | grep -oE '^[[:space:]]*[A-Z_]+' | tr -d ' ' | sort | tr '\n' ' ')
  for k in NEXT_PUBLIC_API_URL API_INTERNAL_URL NEXT_PUBLIC_AUTH_STRICT NEXT_PUBLIC_DEMO_EMAIL NEXT_PUBLIC_DEMO_PASSWORD; do
    case " $names" in *" $k "*) ;; *) row "vercel env $k" DRIFT "missing"; esac
  done
  row "vercel env names" OK "values are encrypted and cannot be compared"
fi

section "Settings (local vs server, resolved with code defaults)"
if remote true 2>/dev/null; then
  srv=$(remote 'cat ~/kairos/.env' 2>/dev/null); loc=$(cat .env)
  for k in KAIROS_PHASE MODEL_GATE_ENFORCE TIMESTAMP_DRIFT_ENFORCE TIMESTAMP_DRIFT_TOLERANCE_MINUTES PLANT_STATE_DEFAULT \
           MAX_UPLOAD_MB AUTH_CACHE_TTL_SECONDS DEDUP_WINDOW_MINUTES LATE_ARRIVAL_WINDOW_MINUTES LEGACY_ROLE_FALLBACK \
           NVIDIA_NIM_DISABLE_THINKING NVIDIA_NIM_NER_TIMEOUT NVIDIA_NIM_TIMEOUT; do
    a=$(effective "$k" "$loc"); b=$(effective "$k" "$srv")
    [ "$a" = "$b" ] || row "$k" DRIFT "local '$a' vs server '$b'"
  done
  req="MOC_WEBHOOK_SECRET CONNECTOR_SHARED_SECRET INTERNAL_API_KEY APP_ENV SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY NEO4J_URI QDRANT_URL CORS_ORIGINS"
  for k in $req; do printf '%s\n' "$srv" | grep -qE "^$k=" || row "server .env $k" DRIFT "missing"; done
  printf '%s\n' "$srv" | grep -qE '^APP_ENV=production' && row "server APP_ENV" OK "production" || row "server APP_ENV" DRIFT "not production"
  row "setting flags" OK "checked $(echo KAIROS_PHASE MODEL_GATE_ENFORCE TIMESTAMP_DRIFT_ENFORCE TIMESTAMP_DRIFT_TOLERANCE_MINUTES PLANT_STATE_DEFAULT MAX_UPLOAD_MB AUTH_CACHE_TTL_SECONDS DEDUP_WINDOW_MINUTES LATE_ARRIVAL_WINDOW_MINUTES LEGACY_ROLE_FALLBACK NVIDIA_NIM_DISABLE_THINKING NVIDIA_NIM_NER_TIMEOUT NVIDIA_NIM_TIMEOUT | wc -w | tr -d ' ') flags"
fi
miss=$(comm -23 <(grep -oE '^[A-Z][A-Z0-9_]+=' .env.example | tr -d '=' | sort) <(grep -oE '^[A-Z][A-Z0-9_]+=' .env | tr -d '=' | sort) | tr '\n' ' ')
[ -z "$miss" ] && row "local .env vs .env.example" OK "same names" || row "local .env vs .env.example" DRIFT "missing locally: $miss"
for k in NEXT_PUBLIC_DEMO_EMAIL NEXT_PUBLIC_DEMO_PASSWORD; do
  [ -n "$(grep -E "^$k=" .env | cut -d= -f2-)" ] || row "local $k" DRIFT "blank, so the local demo button is hidden"
done
[ "$(grep -E '^NEXT_PUBLIC_AUTH_STRICT=' .env | cut -d= -f2-)" = "true" ] && row "local AUTH_STRICT" OK "true, like Vercel" || row "local AUTH_STRICT" DRIFT "Vercel uses true"

section "Local containers"
epoch() { python3 -c "import sys,datetime as d;print(int(d.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00')[:26]+'+00:00').timestamp()))" "$1"; }
newest() { git ls-files -co --exclude-standard -- "$@" | xargs -I{} stat -f %m "{}" 2>/dev/null | sort -n | tail -1; }
check_image() { # $1 label, $2 image, $3.. source paths
  local label=$1 image=$2; shift 2
  local created; created=$(docker image inspect "$image" --format '{{.Created}}' 2>/dev/null)
  [ -n "$created" ] || { row "$label image" UNKNOWN "$image not built"; return; }
  local img src; img=$(epoch "$created"); src=$(newest "$@")
  if [ "${src:-0}" -le "$img" ]; then row "$label image" OK "built after the last source change"
  else row "$label image" DRIFT "older than its source (run: make local-refresh)"; fi
}
opa_started=$(docker inspect kairos-opa --format '{{.State.StartedAt}}' 2>/dev/null)
if [ -n "$opa_started" ]; then
  if [ "$(epoch "$opa_started")" -ge "$(newest infra/policies)" ]; then row "local kairos-opa" OK "started after the policy last changed"
  else row "local kairos-opa" DRIFT "running an older policy (run: docker restart kairos-opa)"; fi
fi
check_image "backend" kairos-backend:local backend/requirements.txt backend/Dockerfile
check_image "frontend" kairos-frontend:local frontend
check_image "connector" kairos-connector:local backend/connectors

if [ "$DEEP" = "1" ]; then
  head "Live logins (--deep)"
  pw=$(grep -E '^KAIROS_SEED_PASSWORD_DEMO=' .env | cut -d= -f2-)
  tok=$(curl -s -m 30 -X POST "$API_URL/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"demo@kairos.local\",\"password\":\"$pw\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)
  role=$(curl -s -m 30 -H "Authorization: Bearer $tok" "$API_URL/auth/me" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("role",""))' 2>/dev/null)
  [ "$role" = "demo" ] && row "demo login on live API" OK "role demo" || row "demo login on live API" DRIFT "role '$role'"
fi

echo
if [ "$bad" = "0" ]; then echo "IN SYNC"; else echo "DRIFT FOUND (see rows above that are not OK)"; fi
exit "$bad"
