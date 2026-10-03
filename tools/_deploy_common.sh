#!/usr/bin/env bash
# Shared settings for tools/sync_check.sh, tools/deploy_backend.sh and tools/deploy_frontend.sh.
# Sourced, never run. One place for the host, the key and the rsync excludes, so the drift check
# and the deploy can never disagree about which files count.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH_KEY="${KAIROS_SSH_KEY:-$HOME/.ssh/kairos-aws.pem}"
SERVER="${KAIROS_SERVER:-ubuntu@kairos-deterium.duckdns.org}"
API_URL="${KAIROS_API_URL:-https://kairos-deterium.duckdns.org}"
WEB_URL="${KAIROS_WEB_URL:-https://kairos-deterium.vercel.app}"
VERCEL_SCOPE="${KAIROS_VERCEL_SCOPE:-kr1shnasomani-preview}"
SSH_OPTS=(-i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=20)

# Everything the backend server must NOT receive: the frontend (Vercel hosts it), git history, local
# tooling, the dev compose override, and every .env (the server keeps its own).
RSYNC_EXCLUDES=(
  --exclude '.git' --exclude 'frontend' --exclude 'node_modules' --exclude '__pycache__'
  --exclude '.pytest_cache' --exclude '.ruff_cache' --exclude '.claude' --exclude '.agents'
  --exclude '.vercel' --exclude 'docker-compose.override.yml'
  --exclude '.env' --exclude '.env.bak' --exclude '.env.bak.*' --exclude '.DS_Store'
)

remote() { ssh "${SSH_OPTS[@]}" "$SERVER" "$@"; }

# A hash of every frontend file that would be uploaded to Vercel (tracked or not, minus ignored).
frontend_hash() {
  (cd "$ROOT" && git ls-files -co --exclude-standard -z frontend docs | xargs -0 shasum | shasum | cut -c1-12)
}
