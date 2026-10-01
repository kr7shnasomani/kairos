#!/usr/bin/env bash
# Capture the product screenshots embedded in the public landing page.
#
# Runs against the live stack so the marketing page shows a real render of the
# app rather than a mockup. Re-run after UI changes; output is committed under
# frontend/public/shots/.
#
#   make dev              # stack must be up
#   ./tools/capture_landing_shots.sh
#
# Uses agent-browser (already installed) driving Chrome over CDP from the host,
# so it reaches localhost directly: no container image, and none of the CORS or
# cross-origin dev-server problems that come with driving the app from inside
# the compose network.
set -euo pipefail

BASE="${KAIROS_URL:-http://localhost:3000}"
API="${KAIROS_API_URL:-http://localhost:8000}"
EMAIL="${KAIROS_EMAIL:-admin@kairos.local}"
# The admin password lives in .env (gitignored), never in this file.
PASSWORD="${KAIROS_PASSWORD:-${KAIROS_SEED_PASSWORD_ADMIN:-}}"
if [ -z "$PASSWORD" ] && [ -f "$(dirname "$0")/../.env" ]; then
  PASSWORD=$(grep -E '^KAIROS_SEED_PASSWORD_ADMIN=' "$(dirname "$0")/../.env" | head -1 | cut -d= -f2-)
fi
[ -n "$PASSWORD" ] || { echo "Set KAIROS_PASSWORD or KAIROS_SEED_PASSWORD_ADMIN (see .env.example)" >&2; exit 2; }
OUT="${OUT_DIR:-$(cd "$(dirname "$0")/.." && pwd)/frontend/public/shots}"

# 16:9 at the app's design width, captured at 2x so it stays sharp on retina.
VW=1440
VH=810
DPR=2

# route|filename
SHOTS=(
  "/management|workspace"
  "/rca|reliability"
  "/briefs|field"
  "/compliance|compliance"
  "/governance/quarantine|turnaround"
  "/offboarding|offboarding"
  "/graph|graph"
)

mkdir -p "$OUT"

echo "authenticating against $API"
TOKEN=$(curl -sS -m 30 -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))')
[ -n "$TOKEN" ] || { echo "login failed"; exit 1; }
echo "authenticated as $EMAIL"

agent-browser set viewport "$VW" "$VH" "$DPR" >/dev/null

# Seed the token the app reads from localStorage. Driving the login form is
# unreliable here: before React hydrates the form submits as a native GET, which
# fails to log in and puts the password in the URL.
agent-browser open "$BASE/login" >/dev/null
agent-browser eval "localStorage.setItem('kairos-token', '$TOKEN')" >/dev/null

failures=0
for entry in "${SHOTS[@]}"; do
  route="${entry%%|*}"
  name="${entry##*|}"

  agent-browser open "$BASE$route" >/dev/null
  agent-browser wait --load networkidle >/dev/null 2>&1 || true
  sleep 3

  # agent-browser wraps results as {"success":…,"data":{"origin":…,"result":…},"error":…}.
  # This read `result` at the TOP level, so `landed` was always empty and the guard below —
  # `[ -n "$landed" ]` — skipped the redirect check on every route it has ever run. A page that
  # bounced to /login was screenshotted and reported as a success.
  landed=$(agent-browser eval "location.pathname" --json 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["result"])' 2>/dev/null || echo "")
  if [ -z "$landed" ]; then
    # Empty now means the eval itself failed. Say so rather than silently skipping the check,
    # which is exactly how the bug above stayed invisible.
    echo "  FAILED $name.png: could not read location.pathname (agent-browser eval failed)"
    failures=$((failures + 1))
    continue
  fi
  if [ "$landed" != "$route" ]; then
    echo "  FAILED $name.png: redirected $route -> $landed"
    failures=$((failures + 1))
    continue
  fi

  # A 404 renders cleanly and would otherwise be captured silently.
  if agent-browser eval "document.body.innerText" 2>/dev/null | grep -qi "page not found"; then
    echo "  FAILED $name.png: $route rendered the 404 page"
    failures=$((failures + 1))
    continue
  fi

  agent-browser screenshot "$OUT/$name.png" >/dev/null
  echo "  wrote $name.png  ($route)"
done

agent-browser close >/dev/null 2>&1 || true

if [ "$failures" -gt 0 ]; then
  echo "done with $failures failure(s)"
  exit 1
fi
echo "done, all shots captured"
