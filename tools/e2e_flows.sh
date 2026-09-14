#!/usr/bin/env bash
# End-to-end flow checks against the running stack, driven through the real UI and API.
#
# The unit tiers cannot see the bugs that matter at a demo — a page that 404s a write, a role that can
# open a screen but not call its API, a timeline that shows every event twice. This walks the flows a
# reviewer will click, as each persona, and fails loudly on an error screen, a console error, a wrong
# redirect or a missing refusal.
#
#   make dev && make load-dataset     # stack up, demo data loaded
#   ./tools/e2e_flows.sh              # safe on demo data: changes no workflow state
#   ./tools/e2e_flows.sh --mutate     # also signs a PTW, raises + resolves a deviation, supersedes a doc
#
# Default mode changes no workflow state; Copilot and RCA calls do append audit-log rows, as every use
# does. --mutate leaves signed briefs, a resolved deviation and a superseded document behind — run it on
# a stack you will reset, never on the dataset you are about to demo or benchmark.
#
# Uses agent-browser (host-installed, like tools/capture_landing_shots.sh), one browser session per
# persona so signed-in identities never leak into each other. Plain bash 3.2 (macOS default): no
# associative arrays.
set -uo pipefail

BASE="${KAIROS_URL:-http://localhost:3000}"
API="${KAIROS_API_URL:-http://localhost:8000}"
MUTATE=0
[ "${1:-}" = "--mutate" ] && MUTATE=1
BODY=$(mktemp -t kairos_e2e_body)

pass=0
fail=0
ok()  { pass=$((pass + 1)); echo "  PASS  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL  $1"; }

password_for() {
  case "$1" in
    admin) echo 'KairosAdmin123!' ;;
    engineer) echo 'KairosEngineer123!' ;;
    reliability) echo 'KairosReliability123!' ;;
    compliance) echo 'KairosCompliance123!' ;;
    field_worker) echo 'KairosField123!' ;;
  esac
}

login() {
  curl -sS -m 30 -X POST "$API/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1@kairos.local\",\"password\":\"$(password_for "$1")\"}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))'
}

api() {  # api <token> <METHOD> <path> [json-body] -> prints "<status> <body>"
  local code
  if [ -n "${4:-}" ]; then
    code=$(curl -sS -m 150 -o "$BODY" -w '%{http_code}' -X "$2" "$API$3" \
      -H "Authorization: Bearer $1" -H 'Content-Type: application/json' -d "$4")
  else
    code=$(curl -sS -m 150 -o "$BODY" -w '%{http_code}' -X "$2" "$API$3" -H "Authorization: Bearer $1")
  fi
  printf '%s ' "$code"
  cat "$BODY"
}

json() { python3 -c "import sys,json; d=json.load(sys.stdin); $1"; }

signin() {  # signin <persona> <token>
  export AGENT_BROWSER_SESSION="e2e-$1"
  agent-browser open "$BASE/login" >/dev/null
  agent-browser eval "localStorage.setItem('kairos-token', '$2')" >/dev/null
}

visit() {  # visit <route> <expected-pathname>
  agent-browser console --clear >/dev/null 2>&1 || true
  agent-browser open "$BASE$1" >/dev/null
  agent-browser wait --load networkidle >/dev/null 2>&1 || true
  sleep 4
  local where text errors
  where=$(agent-browser eval "location.pathname" --json 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["result"])' 2>/dev/null)
  text=$(agent-browser eval "(document.querySelector('main')||document.body).innerText" 2>/dev/null)
  errors=$(agent-browser console 2>&1 | grep -E '^\[error\]' | grep -vE 'hmr|webpack|DevTools' | head -1)
  if [ "$where" != "$2" ]; then bad "$AGENT_BROWSER_SESSION $1 landed on '$where', expected $2"; return; fi
  if echo "$text" | grep -qiE "something went wrong|couldn.t load|page not found|data is unavailable"; then
    bad "$AGENT_BROWSER_SESSION $1 shows an error screen"; return
  fi
  if [ -n "$errors" ]; then bad "$AGENT_BROWSER_SESSION $1 console: ${errors:0:140}"; return; fi
  ok "$AGENT_BROWSER_SESSION $1"
}

command -v agent-browser >/dev/null || { echo "agent-browser is not installed"; exit 2; }
curl -sS -m 10 -o /dev/null "$API/health/" || { echo "API not reachable at $API"; exit 2; }

ADMIN=$(login admin); ENGINEER=$(login engineer); RELIABILITY=$(login reliability)
COMPLIANCE=$(login compliance); FIELD=$(login field_worker)
for t in "$ADMIN" "$ENGINEER" "$RELIABILITY" "$COMPLIANCE" "$FIELD"; do
  [ -n "$t" ] || { echo "a persona login failed"; exit 2; }
done

echo "== 1. Pages and role routing"
signin admin "$ADMIN"
for route in /management /briefs /copilot /assets /assets/EQ-101 /assets/register /assets/bootstrap /events /rca /graph /compliance \
             /compliance/audit-pack /governance /governance/quarantine /governance/conflicts /governance/moc \
             /governance/model-gate /governance/timestamp-drift /governance/push-volume-gate \
             /management/cross-site /audit /documents /documents/compare /offboarding /system-health; do
  visit "$route" "$route"
done
signin field_worker "$FIELD"
for route in /briefs /field/deviation /field/voice; do visit "$route" "$route"; done
visit /management /briefs      # staff surfaces redirect field workers to their inbox
visit /governance /briefs
signin compliance "$COMPLIANCE"
visit /compliance /compliance
visit /audit /audit
visit /governance /compliance  # compliance is read-only: governance redirects to its cockpit

echo "== 2. The API enforces the same boundaries"
status=$(api "$FIELD" GET /governance/quarantine | cut -d' ' -f1)
[ "$status" = 403 ] && ok "field worker refused the quarantine API" || bad "field worker quarantine API returned $status"
ptw=$(api "$ENGINEER" GET "/briefs/?unacknowledged_only=false&limit=20" | cut -d' ' -f2- \
  | json 'print(next((b["brief_id"] for b in d.get("briefs",[]) if b.get("requires_countersignature")), ""))')
if [ -n "$ptw" ]; then
  status=$(api "$ENGINEER" POST "/briefs/$ptw/countersign" '{}' | cut -d' ' -f1)
  [ "$status" = 403 ] && ok "engineer refused a PTW countersignature" || bad "engineer countersign returned $status"
else
  bad "no PTW brief in the engineer inbox"
fi

echo "== 3. Copilot answers with sources, and refuses a safety-critical parameter"
ask() {  # ask <question> -> synthesize response JSON, built the way the Copilot UI builds it (search, then synthesize)
  local q ctx
  q=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1")
  ctx=$(api "$ENGINEER" GET "/search/?q=$q&limit=6" | cut -d' ' -f2- | json 'print(json.dumps(d.get("results", [])))')
  api "$ENGINEER" POST /search/synthesize \
    "$(python3 -c 'import sys,json; print(json.dumps({"query": sys.argv[1], "context": json.loads(sys.argv[2])}))' "$1" "$ctx")" \
    | cut -d' ' -f2-
}
ask "What mechanical seal part number should be used for pump EQ-101?" \
  | json 'sys.exit(0 if "FSL-2240B" in (d.get("answer") or "") and d.get("sources") and not d.get("refused") else 1)' \
  && ok "seal part number answered (FSL-2240B) with sources" || bad "seal part number answer missing, wrong or unsourced"
# Safety-critical: with no authoritative same-asset source, the gate must refuse rather than hedge.
ask "What is the maximum operating pressure engineers should use for HE-302?" \
  | json 'sys.exit(0 if d.get("refused") else 1)' \
  && ok "HE-302 pressure limit refused" || bad "HE-302 pressure limit was answered instead of refused"

echo "== 4. RCA pack and audit pack are well formed"
api "$ENGINEER" POST /search/rca-pack \
  '{"asset_id":"EQ-101","failure_code":"SEAL-FAIL","incident_date":"2026-07-15T00:00:00Z","include_quarantine":true}' | cut -d' ' -f2- \
  | json 'ids=[e.get("event_id") for e in d.get("timeline") or [] if e.get("event_id")]; sys.exit(0 if d.get("hypotheses") and len(ids)==len(set(ids)) else 1)' \
  && ok "RCA pack has hypotheses and no duplicated timeline events" || bad "RCA pack missing hypotheses or shows an event twice"
api "$COMPLIANCE" GET "/compliance/audit-pack?framework=OISD_117" | cut -d' ' -f2- \
  | json 'sys.exit(0 if all(len({e["document_id"] for e in c["evidence"]})==len(c["evidence"]) for c in d.get("clauses") or []) else 1)' \
  && ok "audit pack lists each evidence document once" || bad "audit pack repeats evidence documents"

if [ "$MUTATE" = 1 ]; then
  echo "== 5. (--mutate) PTW dual sign-off"
  if [ -n "$ptw" ]; then
    status=$(api "$ENGINEER" POST "/briefs/$ptw/ack" '{"signature":"E2E Engineer"}' | cut -d' ' -f1)
    [ "$status" = 200 ] && ok "engineer acknowledged the PTW" || bad "PTW acknowledgment returned $status"
    status=$(api "$RELIABILITY" POST "/briefs/$ptw/countersign" '{}' | cut -d' ' -f1)
    [ "$status" = 200 ] && ok "reliability countersigned the PTW" || bad "PTW countersign returned $status"
    names=$(api "$RELIABILITY" GET "/briefs/$ptw" | cut -d' ' -f2- \
      | json 'print(d.get("acknowledged_by_name") or "", "|", d.get("countersigned_by_name") or "")')
    case "$names" in " | "*|*"| ") bad "signers not shown by name: '$names'" ;; *) ok "signers shown by name: $names" ;; esac
  fi

  echo "== 6. (--mutate) Deviation raised in the field, resolved by engineering"
  item=$(api "$FIELD" POST /events/deviation-flag \
    '{"asset_id":"PG-18","description":"E2E check: gauge reading drifts under load"}' | cut -d' ' -f2- \
    | json 'print(d.get("item_id",""))')
  if [ -n "$item" ]; then
    ok "field worker raised a deviation"
    status=$(api "$FIELD" POST "/events/deviation-flag/$item/resolve" '{"resolution":"disputed"}' | cut -d' ' -f1)
    [ "$status" = 403 ] && ok "field worker refused resolving it" || bad "field worker resolve returned $status"
    status=$(api "$ENGINEER" POST "/events/deviation-flag/$item/resolve" \
      '{"resolution":"disputed","notes":"E2E check"}' | cut -d' ' -f1)
    [ "$status" = 200 ] && ok "engineer resolved the deviation" || bad "engineer resolve returned $status"
  else
    bad "deviation flag was not accepted"
  fi

  echo "== 7. (--mutate) Supersede a document through the UI"
  replacement="$(mktemp -t kairos_e2e_sop).txt"
  printf 'SOP-HE-GEN-11 Rev E2E - next scheduled review due 2028-03-01.\n' > "$replacement"
  doc=$(api "$ENGINEER" GET "/documents/?limit=100" | cut -d' ' -f2- \
    | json 'd=d.get("documents",d.get("items",d)) if isinstance(d,dict) else d; print(next((x["document_id"] for x in d if x.get("file_name")=="sop_he_gen_11.pdf" and x.get("status")!="superseded"),""))')
  if [ -n "$doc" ]; then
    signin engineer "$ENGINEER"
    agent-browser open "$BASE/documents/$doc" >/dev/null
    agent-browser wait --load networkidle >/dev/null 2>&1 || true
    sleep 4
    agent-browser find role button click --name "Supersede document" >/dev/null 2>&1
    sleep 2
    agent-browser upload 'input[type=file]' "$replacement" >/dev/null 2>&1
    agent-browser find role button click --name "Confirm supersede" >/dev/null 2>&1
    sleep 12
    state=$(api "$ENGINEER" GET "/documents/$doc" | cut -d' ' -f2- | json 'print(d.get("status"))')
    [ "$state" = superseded ] && ok "sop_he_gen_11.pdf superseded through the UI" || bad "supersede left the document '$state'"
  else
    bad "no active sop_he_gen_11.pdf to supersede"
  fi
  rm -f "$replacement"
fi

rm -f "$BODY"
for persona in admin compliance field_worker engineer; do
  AGENT_BROWSER_SESSION="e2e-$persona" agent-browser close >/dev/null 2>&1 || true
done

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
