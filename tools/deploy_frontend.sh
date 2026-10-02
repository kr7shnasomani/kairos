#!/usr/bin/env bash
# Deploy this working tree's frontend to Vercel production, built on Vercel's servers.
#
#   make deploy-frontend            # asks for confirmation
#   tools/deploy_frontend.sh --yes
#
# Why a remote build: `vercel pull` returns empty values for the encrypted environment variables, so
# a local `vercel build` would bake a blank NEXT_PUBLIC_API_URL into the site. The project is linked
# at the repo root (root directory `frontend` is set in the Vercel project). Nothing is pushed to
# GitHub. NEXT_PUBLIC_* values are baked at build time, so changing one in Vercel needs this deploy.
set -euo pipefail
# shellcheck source=tools/_deploy_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_deploy_common.sh"
cd "$ROOT"

command -v vercel >/dev/null || { echo "vercel CLI not installed" >&2; exit 2; }
vercel whoami >/dev/null 2>&1 || { echo "not logged in: run 'vercel login'" >&2; exit 2; }
[ -f .vercel/project.json ] || vercel link --yes --project kairos --scope "$VERCEL_SCOPE"

if [ "${1:-}" != "--yes" ]; then
  echo "This replaces the live site at $WEB_URL with the frontend in this working tree."
  read -r -p "Type 'deploy' to continue: " ok; [ "$ok" = "deploy" ] || { echo "aborted"; exit 1; }
fi

HASH=$(frontend_hash)
vercel deploy --prod --yes --scope "$VERCEL_SCOPE"
printf '%s\n' "$HASH" > .vercel/deployed-frontend.sha

curl -s -m 20 "$WEB_URL/login" | grep -q "Explore the live demo" && echo "verified: demo button is live" \
  || echo "WARNING: the demo button is not on the live login page" >&2
echo "recorded frontend hash $HASH. next: tools/sync_check.sh"
