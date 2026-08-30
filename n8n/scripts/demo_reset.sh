#!/usr/bin/env bash
# =============================================================================
# AIPP · Demo Reset Script
# =============================================================================
# One-command reset for the MS defense demo:
#
#   1. Delete every finished/waiting execution from n8n (clean UI list).
#   2. Fire every HITL webhook with a realistic sample payload.
#   3. (optional) Auto-approve or auto-reject all fresh waiting executions
#      after a short pause so the demo shows a full green lifecycle.
#
# Two-command flow — no more manual clicks between rehearsals:
#
#     bash scripts/demo_reset.sh              # clean + fire, wait for human clicks
#     bash scripts/demo_reset.sh approve      # clean + fire + auto-approve
#     bash scripts/demo_reset.sh reject       # clean + fire + auto-reject
#     bash scripts/demo_reset.sh --keep       # skip cleanup, only fire fresh
#
# Requires: N8N_BASE_URL, N8N_API_KEY exported (source ../.env first).
# =============================================================================
set -euo pipefail

# ---- args -------------------------------------------------------------------
DECISION=""
KEEP=0
for arg in "$@"; do
    case "$arg" in
        approve|reject) DECISION="$arg" ;;
        --keep)         KEEP=1 ;;
        -h|--help)      sed -n '2,20p' "$0"; exit 0 ;;
        *)              echo "Unknown arg: $arg"; exit 1 ;;
    esac
done

: "${N8N_BASE_URL:?N8N_BASE_URL not set — run: source ../.env && export N8N_BASE_URL N8N_API_KEY}"
: "${N8N_API_KEY:?N8N_API_KEY not set}"

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 AIPP-Demo-Reset"
BASE="${N8N_BASE_URL%/}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "═══════════════════════════════════════════════════════════════"
echo " AIPP · Demo Reset"
echo " target n8n : $BASE"
echo " cleanup    : $([[ $KEEP -eq 1 ]] && echo skipped || echo yes)"
echo " decision   : ${DECISION:-manual (no auto-approve)}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# =============================================================================
# STEP 1 — delete every past execution (fresh slate)
# =============================================================================
if [[ $KEEP -eq 0 ]]; then
    echo "STEP 1 — clearing past executions"
    echo "---------------------------------"
    curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
        "$BASE/api/v1/executions?limit=250" | \
    BASE="$BASE" UA="$UA" API_KEY="$N8N_API_KEY" python3 <<'PY'
import json, os, sys, urllib.request, urllib.error

BASE    = os.environ["BASE"].rstrip("/")
UA      = os.environ["UA"]
API_KEY = os.environ["API_KEY"]

raw = sys.stdin.read()
if not raw.strip():
    print("  ✗ n8n API returned empty body — nothing to clean")
    sys.exit(0)

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("  ✗ n8n API did not return JSON. First 400 chars:")
    print(raw[:400])
    sys.exit(1)

execs = data.get("data", data) if isinstance(data, dict) else data
if not execs:
    print("  (nothing to delete — server is already clean)")
    sys.exit(0)

print(f"  found {len(execs)} execution(s) to delete")
ok = fail = 0
for e in execs:
    eid = e.get("id")
    if eid is None:
        continue
    req = urllib.request.Request(
        f"{BASE}/api/v1/executions/{eid}",
        headers={"X-N8N-API-KEY": API_KEY, "User-Agent": UA},
        method="DELETE",
    )
    try:
        urllib.request.urlopen(req, timeout=15)
        ok += 1
    except urllib.error.HTTPError as ex:
        # 404 = already gone. Anything else = surface but keep going.
        if ex.code != 404:
            print(f"    ✗ exec {eid}: HTTP {ex.code}")
            fail += 1
        else:
            ok += 1
    except Exception as ex:                                        # noqa: BLE001
        print(f"    ✗ exec {eid}: {ex}")
        fail += 1
print(f"  ✓ deleted {ok} · failed {fail}")
PY
    echo ""
fi

# =============================================================================
# STEP 2 — fire every HITL webhook with a fresh sample payload
# =============================================================================
echo "STEP 2 — firing HITL webhooks with realistic sample data"
echo "--------------------------------------------------------"

# Each HITL flow gets its own realistic payload so the Slack cards look
# credible during a live demo (no more `pod=xxx` placeholder text).
declare -A PAYLOADS=(
    ["aipp-troubleshoot"]='{"text":"pod=coredns-589f44dc88-7wnj5 ns=kube-system"}'
    ["aipp-grafana"]='{"commonLabels":{"alertname":"HighMemoryUsage","severity":"warning","instance":"api-checkout-1"},"commonAnnotations":{"description":"container memory at 92%","value":"92%"},"alerts":[{"status":"firing","labels":{"alertname":"HighMemoryUsage","instance":"api-checkout-1"}}]}'
    ["aipp-incident"]='{"summary":"payments-svc latency spike","service_id":"payments-svc","severity":"Sev2","data":{"essentials":{"alertRule":"payments-latency-p99","severity":"Sev2"}}}'
    ["aipp-pipeline-review"]='{"run_id":"demo-run-'"$RANDOM"'","pipeline_yaml":"stages:\n  - build\n  - deploy_prod\nsteps:\n  - name: deploy\n    action: kubectl apply -f prod/","targets":["aws","azure"]}'
)

for path in "${!PAYLOADS[@]}"; do
    payload="${PAYLOADS[$path]}"
    code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
        "$BASE/webhook/$path" \
        -A "$UA" \
        -H 'Content-Type: application/json' \
        -d "$payload")
    if [[ "$code" == "200" ]]; then
        echo "  ✓ /webhook/$path                       HTTP $code"
    else
        echo "  ✗ /webhook/$path                       HTTP $code  (workflow may be inactive)"
    fi
done

echo ""
echo "STEP 3 — waiting 8s for workflows to park at their Wait nodes..."
sleep 8

# =============================================================================
# STEP 4 — optional auto-approve / auto-reject
# =============================================================================
if [[ -z "$DECISION" ]]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo " Demo reset done. Approvals await human clicks in Slack."
    echo " • Slack channel: #aipp — click Approve / Reject on each card."
    echo " • n8n UI → Executions: see the waiting flows."
    echo " • To auto-approve later:  bash scripts/hitl_demo.sh approve"
    echo "═══════════════════════════════════════════════════════════════"
    exit 0
fi

echo ""
echo "STEP 4 — auto-$DECISION-ing every waiting execution"
echo "----------------------------------------------------"
DECISION="$DECISION" bash "$SCRIPT_DIR/hitl_demo.sh" "$DECISION" || true

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " Demo reset complete."
echo " • Every HITL card in Slack should be sealed with $DECISION."
echo " • n8n UI → Executions should show full green run graphs."
echo "═══════════════════════════════════════════════════════════════"
