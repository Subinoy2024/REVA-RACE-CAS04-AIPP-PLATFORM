#!/usr/bin/env bash
# =============================================================================
# AIPP · HITL Demo Runner
# =============================================================================
# Fires every HITL-enabled webhook workflow in sequence, waits for each to
# park in "waiting" state, then auto-clicks the APPROVE (or REJECT) link
# by hitting the resumeUrl exposed on the Wait node.
#
# Great for MS-defense demo — one command shows every human-in-the-loop
# workflow going through its full lifecycle end-to-end.
#
# Requires: N8N_BASE_URL, N8N_API_KEY exported (source ../.env first).
# Optional first arg:  approve | reject   (default: approve)
# =============================================================================
set -euo pipefail

DECISION="${1:-approve}"
if [[ "$DECISION" != "approve" && "$DECISION" != "reject" ]]; then
    echo "Usage: $0 [approve|reject]"
    exit 1
fi

: "${N8N_BASE_URL:?N8N_BASE_URL not set — run: source ../.env && export N8N_BASE_URL N8N_API_KEY}"
: "${N8N_API_KEY:?N8N_API_KEY not set}"

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 AIPP-HITL-Demo"
BASE="${N8N_BASE_URL%/}"

echo "═══════════════════════════════════════════════════════════════"
echo " AIPP · HITL Demo Runner"
echo " target n8n : $BASE"
echo " decision   : $DECISION (applied to every workflow)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ---- 1. fire every HITL webhook -----------------------------------------
declare -A PAYLOADS=(
    ["aipp-troubleshoot"]='{"text":"pod=coredns-589f44dc88-7wnj5 ns=kube-system"}'
    ["aipp-grafana"]='{"commonLabels":{"alertname":"HighMemoryUsage","instance":"api-checkout-1"},"commonAnnotations":{"value":"92%"}}'
    ["aipp-incident"]='{"summary":"payments-svc latency spike","service_id":"payments-svc","severity":"Sev2"}'
    ["aipp-pipeline-review"]='{"run_id":"demo-run-42","pipeline_yaml":"stages:\n  - build\n  - deploy","targets":["aws"]}'
)

echo "STEP 1 — firing HITL webhooks"
echo "-----------------------------"
for path in "${!PAYLOADS[@]}"; do
    payload="${PAYLOADS[$path]}"
    code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
        "$BASE/webhook/$path" \
        -H 'Content-Type: application/json' \
        -d "$payload")
    if [[ "$code" == "200" ]]; then
        echo "  ✓ /webhook/$path                       HTTP $code"
    else
        echo "  ✗ /webhook/$path                       HTTP $code  (workflow may be inactive)"
    fi
done

echo ""
echo "STEP 2 — waiting 6s for workflows to reach Wait node..."
sleep 6

# ---- 2. list all waiting executions -------------------------------------
echo ""
echo "STEP 3 — locating waiting executions and auto-$DECISION-ing each"
echo "-----------------------------------------------------------------"

curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
    "$BASE/api/v1/executions?limit=100" | \
DECISION="$DECISION" BASE="$BASE" UA="$UA" API_KEY="$N8N_API_KEY" python3 <<'PY'
import json, sys, os, urllib.request, urllib.error, time

DECISION = os.environ["DECISION"]
BASE     = os.environ["BASE"].rstrip("/")
UA       = os.environ["UA"]
API_KEY  = os.environ["API_KEY"]

raw = sys.stdin.read()
if not raw.strip():
    print("  ✗ n8n API returned empty body — check network/auth")
    sys.exit(1)
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("  ✗ n8n API did not return JSON. First 400 chars of response:")
    print(raw[:400])
    sys.exit(1)
execs = data.get("data", data) if isinstance(data, dict) else data
# n8n API returns ALL executions — filter client-side for waiting.
# Different n8n versions expose the state as `status`, `finished`, or
# `stoppedAt`. Waiting = not finished + not stopped.
def is_waiting(e: dict) -> bool:
    if e.get("status") in ("waiting", "running"):
        return True
    if e.get("finished") is False and not e.get("stoppedAt"):
        return True
    return False

execs = [e for e in execs if is_waiting(e)]
print(f"  found {len(execs)} waiting execution(s)")
# n8n's list endpoint doesn't include full runData — we always fetch detail.
if not execs:
    print("  (no waiting executions found — did the webhooks fire on active workflows?)")
    sys.exit(0)

def find_resume_url(execution: dict) -> str | None:
    """Walk the execution's runData to find the Wait node's resumeUrl."""
    run_data = (
        execution.get("data", {}).get("resultData", {}).get("runData", {})
    )
    for node_name, runs in run_data.items():
        for run in runs or []:
            for out_branch in (run.get("data", {}).get("main") or []):
                for item in (out_branch or []):
                    j = item.get("json") or {}
                    # n8n exposes the resume URL either at $execution.resumeUrl
                    # or on the Wait node's output — check both patterns.
                    if isinstance(j, dict):
                        for k in ("resumeUrl", "$execution.resumeUrl"):
                            if k in j and "webhook-waiting" in str(j[k]):
                                return j[k]
    return None

def fetch_execution_detail(eid: str) -> dict:
    req = urllib.request.Request(
        f"{BASE}/api/v1/executions/{eid}?includeData=true",
        headers={"X-N8N-API-KEY": API_KEY, "User-Agent": UA},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def hit_resume(url: str) -> tuple[int, str]:
    # Append &a=approve / &a=reject to the resume URL.
    sep = "&" if "?" in url else "?"
    final = f"{url}{sep}a={DECISION}"
    req = urllib.request.Request(final, headers={"User-Agent": UA})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, r.read().decode()[:120]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:120]

for e in execs:
    eid = e.get("id")
    wf_name = e.get("workflowData", {}).get("name") or e.get("workflowId", "?")
    # Fetch full detail (list endpoint may not include full runData)
    try:
        detail = fetch_execution_detail(eid)
        url = find_resume_url(detail)
    except Exception as ex:
        print(f"  ✗ {wf_name} · exec {eid}: {ex}")
        continue

    if not url:
        # Fallback: build the URL manually from a known n8n pattern. n8n also
        # accepts /webhook-waiting/{execId}?a=<x> without a signature when
        # the resume mode is "webhook" (signature is optional in some builds).
        url = f"{BASE}/webhook-waiting/{eid}"
        print(f"  ⚠ {wf_name} · exec {eid}: no signed URL found — trying {url}")

    status, body = hit_resume(url)
    marker = "✓" if status == 200 else ("↺" if status == 409 else "✗")
    print(f"  {marker} {wf_name[:48]:<48} · exec {eid} · HTTP {status} · {body}")
PY

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " Demo done."
echo " • Check Slack #aipp for the approval/rejection cards."
echo " • Check n8n UI → Executions for the full green run graphs."
echo "═══════════════════════════════════════════════════════════════"
