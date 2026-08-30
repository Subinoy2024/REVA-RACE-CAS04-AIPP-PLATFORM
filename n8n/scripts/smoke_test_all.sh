#!/usr/bin/env bash
# =============================================================================
# AIPP · Standalone Workflow Smoke Test  (single-file, zero dependencies)
# =============================================================================
# What it does:
#   1. Rebuilds every workflow JSON  (calls build_workflows.py in-place)
#   2. Pushes every JSON to n8n via REST API + activates them
#   3. Fires each workflow with the right trigger:
#        webhook  → HTTP POST /webhook/<path>
#        form     → HTTP POST /form/<path>  (URL-encoded)
#        schedule → POST /api/v1/workflows/<id>/execute
#        error    → skipped (only fires on other-flow crashes)
#   4. Waits 12 s for executions to park / finish
#   5. Prints a colour-coded pass/fail matrix with the failing node
#      + a fix-hint per failure ("check GITHUB_PAT", "K8S_TOKEN", …)
#   6. Snapshots the AIPP proxy /health to show which local
#      integrations AIPP thinks are configured.
#
# Requires (in the shell before running):
#   N8N_BASE_URL     — required
#   N8N_API_KEY      — required
#   AIPP_BASE_URL    — optional (for the /health snapshot)
#   PROXY_API_KEY    — optional (for the /health snapshot)
#
# Usage:
#   source ../.env && export N8N_BASE_URL N8N_API_KEY PROXY_API_KEY AIPP_BASE_URL
#   bash scripts/smoke_test_all.sh                # full run
#   bash scripts/smoke_test_all.sh --local-only   # skip Azure flows
#   bash scripts/smoke_test_all.sh --skip-deploy  # already deployed
#   bash scripts/smoke_test_all.sh --skip-build   # skip build_workflows.py
# =============================================================================
set -uo pipefail                # no `-e`: one bad flow must not kill the report

# ---- args -------------------------------------------------------------------
LOCAL_ONLY=0; SKIP_DEPLOY=0; SKIP_BUILD=0
for arg in "$@"; do
    case "$arg" in
        --local-only)   LOCAL_ONLY=1 ;;
        --skip-deploy)  SKIP_DEPLOY=1 ;;
        --skip-build)   SKIP_BUILD=1 ;;
        -h|--help)      sed -n '2,32p' "$0"; exit 0 ;;
        *)              echo "Unknown arg: $arg"; exit 1 ;;
    esac
done

: "${N8N_BASE_URL:?N8N_BASE_URL not set — run: source ../.env && export N8N_BASE_URL N8N_API_KEY}"
: "${N8N_API_KEY:?N8N_API_KEY not set}"

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 AIPP-Smoke"
BASE="${N8N_BASE_URL%/}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WF_DIR="${SCRIPT_DIR}/../workflows"
BUILD_SCRIPT="${SCRIPT_DIR}/../build_workflows.py"

# ---- pull env from ../.env if some keys are still missing --------------------
ENV_FILE="${SCRIPT_DIR}/../../.env"
if [[ -f "$ENV_FILE" ]]; then
    while IFS='=' read -r key val; do
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] && continue
        val="${val%$'\r'}"; val="${val#\"}"; val="${val%\"}"
        val="${val#\'}"; val="${val%\'}"
        [[ -z "${!key:-}" ]] && export "$key=$val"
    done < "$ENV_FILE"
fi

# ---- ANSI colours (skip when not a tty) --------------------------------------
if [[ -t 1 ]]; then
    C_OK="\033[0;32m"; C_WARN="\033[1;33m"; C_FAIL="\033[0;31m"
    C_INFO="\033[1;34m"; C_DIM="\033[2m"; C_R="\033[0m"; C_BOLD="\033[1m"
else
    C_OK=""; C_WARN=""; C_FAIL=""; C_INFO=""; C_DIM=""; C_R=""; C_BOLD=""
fi

echo -e "${C_BOLD}════════════════════════════════════════════════════════════════${C_R}"
echo -e "${C_BOLD}  AIPP · Full Workflow Smoke Test${C_R}"
echo -e "  n8n         : ${C_INFO}${BASE}${C_R}"
echo -e "  local-only  : $([[ $LOCAL_ONLY -eq 1 ]] && echo yes || echo no)"
echo -e "  skip-deploy : $([[ $SKIP_DEPLOY -eq 1 ]] && echo yes || echo no)"
echo -e "  skip-build  : $([[ $SKIP_BUILD  -eq 1 ]] && echo yes || echo no)"
echo -e "${C_BOLD}════════════════════════════════════════════════════════════════${C_R}"
echo ""

# =============================================================================
# STEP 1a — rebuild JSON files from build_workflows.py
# =============================================================================
if [[ $SKIP_BUILD -eq 0 && -f "$BUILD_SCRIPT" ]]; then
    echo -e "${C_BOLD}STEP 1a${C_R}  regenerate workflow JSONs from source"
    if ! python3 "$BUILD_SCRIPT" > /tmp/aipp-build.log 2>&1; then
        echo -e "  ${C_FAIL}✗ build_workflows.py failed — see /tmp/aipp-build.log${C_R}"
        tail -20 /tmp/aipp-build.log
        exit 1
    fi
    echo -e "  ${C_OK}✓ workflows rebuilt${C_R}"
    echo ""
fi

if [[ ! -d "$WF_DIR" ]] || [[ -z "$(ls -A "$WF_DIR"/*.json 2>/dev/null)" ]]; then
    echo -e "  ${C_FAIL}✗ no JSONs in $WF_DIR — run build_workflows.py first${C_R}"
    exit 1
fi

# =============================================================================
# STEP 1b — deploy + activate every workflow via the n8n REST API
# =============================================================================
declare -A WF_ID          # workflow filename → n8n workflow id
declare -A WF_NAME        # workflow filename → n8n workflow name

deploy_one() {
    local file="$1"
    local wf_json
    wf_json=$(python3 -c "
import json,sys
d=json.load(open('$file'))
for k in ('active','versionId','meta','staticData','pinData','tags'):
    d.pop(k,None)
print(json.dumps(d))")
    local name
    name=$(python3 -c "import json;print(json.load(open('$file'))['name'])")

    # look up existing by name
    local existing_id
    existing_id=$(curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
        --max-time 20 "$BASE/api/v1/workflows?limit=250" | python3 -c "
import json,sys
d=json.load(sys.stdin)
wfs=d.get('data') or (d if isinstance(d,list) else d.get('data',[]))
m=[w for w in wfs if w.get('name')=='''$name''']
print(m[0]['id'] if m else '')")

    local resp
    if [[ -n "$existing_id" ]]; then
        resp=$(curl -sS -X PUT -A "$UA" \
            -H "X-N8N-API-KEY: $N8N_API_KEY" -H "Content-Type: application/json" \
            --max-time 30 \
            -d "$wf_json" "$BASE/api/v1/workflows/$existing_id")
        local new_id
        new_id=$(echo "$resp" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get('id') or d.get('data',{}).get('id',''))
except Exception:
    print('')")
        echo "$new_id"
    else
        resp=$(curl -sS -X POST -A "$UA" \
            -H "X-N8N-API-KEY: $N8N_API_KEY" -H "Content-Type: application/json" \
            --max-time 30 \
            -d "$wf_json" "$BASE/api/v1/workflows")
        local new_id
        new_id=$(echo "$resp" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get('id') or d.get('data',{}).get('id',''))
except Exception:
    print('')")
        echo "$new_id"
    fi
}

if [[ $SKIP_DEPLOY -eq 0 ]]; then
    echo -e "${C_BOLD}STEP 1b${C_R}  deploy + activate every workflow"
    for f in "$WF_DIR"/*.json; do
        [[ -f "$f" ]] || continue
        base=$(basename "$f")
        name=$(python3 -c "import json;print(json.load(open('$f'))['name'])")
        WF_NAME["$base"]="$name"

        wid=$(deploy_one "$f")
        if [[ -z "$wid" ]]; then
            echo -e "  ${C_FAIL}✗ deploy $name${C_R}"
            continue
        fi
        WF_ID["$base"]="$wid"

        # activate (non-fatal — some Azure workflows may fail without creds)
        act_code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST -A "$UA" \
            -H "X-N8N-API-KEY: $N8N_API_KEY" --max-time 20 \
            "$BASE/api/v1/workflows/$wid/activate")
        if [[ "$act_code" == "200" ]]; then
            printf "  ${C_OK}✓${C_R} %-52s  id=%s activated\n" "$name" "$wid"
        else
            printf "  ${C_WARN}!${C_R} %-52s  id=%s activate=HTTP%s\n" "$name" "$wid" "$act_code"
        fi
    done
    echo ""
else
    echo -e "${C_DIM}(step 1b skipped — assuming workflows already deployed & active)${C_R}"
    # still need the WF_ID / WF_NAME lookup — pull the list once
    WF_LIST_JSON=$(curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
        "$BASE/api/v1/workflows?limit=250")
    for f in "$WF_DIR"/*.json; do
        base=$(basename "$f")
        name=$(python3 -c "import json;print(json.load(open('$f'))['name'])")
        WF_NAME["$base"]="$name"
        wid=$(echo "$WF_LIST_JSON" | python3 -c "
import json,sys
d=json.load(sys.stdin)
wfs=d.get('data') or (d if isinstance(d,list) else d.get('data',[]))
m=[w for w in wfs if w.get('name')=='''$name''']
print(m[0]['id'] if m else '')")
        WF_ID["$base"]="$wid"
    done
fi

# =============================================================================
# STEP 2 — fire every workflow with an appropriate trigger payload
# =============================================================================
echo -e "${C_BOLD}STEP 2${C_R}  fire every workflow"

# Payload map — one entry per webhook path.
declare -A WEBHOOK_PAYLOADS=(
    ["aipp-sub-vending"]='{"team":"platform","cost_center":"cc-42","region":"eastus","tier":"sandbox"}'
    ["aipp-troubleshoot"]='{"text":"pod=coredns-589f44dc88-7wnj5 ns=kube-system"}'
    ["aipp-grafana"]='{"commonLabels":{"alertname":"HighMemoryUsage","severity":"warning","instance":"api-checkout-1"},"commonAnnotations":{"description":"container memory at 92%","value":"92%"},"alerts":[{"status":"firing","labels":{"alertname":"HighMemoryUsage"}}]}'
    ["aipp-incident"]='{"summary":"payments-svc latency spike","service_id":"payments-svc","severity":"Sev2","data":{"essentials":{"alertRule":"payments-latency","severity":"Sev2"}}}'
    ["aipp-sop"]='{"incident_id":"INC-42","incident_summary":"payments latency spike resolved by restart","runbook_topic":"payments-svc restart"}'
    ["aipp-pipeline-review"]='{"run_id":"smoke-'"$RANDOM"'","pipeline_yaml":"stages:\n  - build\n  - deploy","targets":["aws","azure"]}'
)
declare -A FORM_PAYLOADS=(
    ["aipp-self-service-vm-request"]='Requester+email=demo%40aipp.local&Target=proxmox&Workload+description=web+api+3+tier'
    ["aipp-chaos-experiment-request"]='Requester=demo%40aipp.local&Target+namespace=default&Question+to+answer=how+does+the+cluster+behave+under+pod+deletion'
)

# Regex to skip Azure-dependent files with --local-only
AZURE_WORKFLOWS_REGEX='^(04_|09_|12_|13_|15_)'   # #01 is a GH-PR flow — actually local

declare -A FIRE_METHOD    # workflow filename → webhook | form | execute | skipped
declare -A FIRE_HTTP      # workflow filename → HTTP status of the trigger call

for f in "$WF_DIR"/*.json; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    name="${WF_NAME[$base]:-$base}"

    if [[ $LOCAL_ONLY -eq 1 && "$base" =~ $AZURE_WORKFLOWS_REGEX ]]; then
        FIRE_METHOD["$base"]="skipped-azure"
        continue
    fi

    trig_info=$(python3 <<PY
import json
d=json.load(open('$f'))
for n in d['nodes']:
    t=n['type']; p=n['parameters']
    if t=='n8n-nodes-base.webhook':      print('webhook',p.get('path','')); break
    if t=='n8n-nodes-base.formTrigger':  print('form',p.get('path','')); break
    if t=='n8n-nodes-base.scheduleTrigger': print('schedule',''); break
    if t=='n8n-nodes-base.errorTrigger':    print('error',''); break
else: print('unknown','')
PY
)
    kind=$(echo "$trig_info" | awk '{print $1}')
    path=$(echo "$trig_info" | awk '{print $2}')

    case "$kind" in
        webhook)
            payload="${WEBHOOK_PAYLOADS[$path]:-\{\}}"
            code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
                -A "$UA" -H 'Content-Type: application/json' --max-time 20 \
                "$BASE/webhook/$path" -d "$payload")
            FIRE_METHOD["$base"]="webhook /$path"; FIRE_HTTP["$base"]="$code"
            printf "  %-6s /webhook/%-42s  HTTP %s\n" "hook" "$path" "$code"
            ;;
        form)
            payload="${FORM_PAYLOADS[$path]:-}"
            code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
                -A "$UA" -H 'Content-Type: application/x-www-form-urlencoded' --max-time 20 \
                "$BASE/form/$path" -d "$payload")
            FIRE_METHOD["$base"]="form /$path"; FIRE_HTTP["$base"]="$code"
            printf "  %-6s /form/%-45s  HTTP %s\n" "form" "$path" "$code"
            ;;
        schedule)
            # n8n's public REST API does NOT expose a "run scheduled
            # workflow now" endpoint on Community Edition — /execute is
            # internal-only and returns 405. We mark schedules as
            # "verify-in-UI" so the report is honest, not misleading.
            FIRE_METHOD["$base"]="schedule (verify in n8n UI)"
            FIRE_HTTP["$base"]="n/a"
            printf "  %-6s %-52s  ${C_DIM}(schedule — verify manually in n8n UI)${C_R}\n" "sched" "$name"
            ;;
        error)
            FIRE_METHOD["$base"]="error-trigger (skipped)"; FIRE_HTTP["$base"]="---"
            ;;
        *)
            FIRE_METHOD["$base"]="unknown"; FIRE_HTTP["$base"]="000"
            ;;
    esac
done

echo ""
echo -e "${C_DIM}Waiting 20 s for executions to complete or park at Wait nodes…${C_R}"
sleep 20

# =============================================================================
# STEP 3 — pull latest execution per workflow, decide pass / fail / waiting
# =============================================================================
echo ""
echo -e "${C_BOLD}STEP 3${C_R}  execution status per workflow"

EXECS=$(curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
    --max-time 30 "$BASE/api/v1/executions?limit=250")

LATEST_JSON=$(echo "$EXECS" | python3 <<'PY'
import json,sys
try: d=json.loads(sys.stdin.read())
except Exception: print("{}"); raise SystemExit
execs=d.get("data",d) if isinstance(d,dict) else d
latest={}
for e in execs:
    # n8n exposes the workflow id at different paths across versions —
    # try every reasonable one so the smoke test keeps working.
    wid=(str(e.get("workflowId") or "")
         or str((e.get("workflowData") or {}).get("id") or "")
         or str(e.get("workflow_id") or ""))
    if not wid: continue
    key=e.get("startedAt") or e.get("stoppedAt") or e.get("id") or ""
    prev=latest.get(wid)
    if prev is None or (prev.get("startedAt") or prev.get("id") or "")<key:
        latest[wid]=e
print(json.dumps(latest))
PY
)

# fix-hint lookup — keyword in the failing node name → what env to check
fix_hint() {
    local node="$1"
    local err="$2"
    local blob
    blob=$(echo "$node $err" | tr '[:upper:]' '[:lower:]')
    case "$blob" in
        *k8s*|*kubernetes*|*pod*|*kubectl*)
            echo "check K8S_API_URL / K8S_TOKEN in .env (or /api/proxy/health.k8s)" ;;
        *github*|*pull-request*|*repo*|*git*)
            echo "check GITHUB_PAT + GH_REPO_ALLOWLIST in .env" ;;
        *grafana*)
            echo "check GRAFANA_URL / GRAFANA_API_KEY in .env" ;;
        *proxmox*|*vm*)
            echo "check PROXMOX_URL / PROXMOX_TOKEN / PROXMOX_NODE in .env" ;;
        *azure*|*arm*|*token*exchange*|*get*token*|*subscription*)
            echo "Azure — needs AZURE_TENANT_ID / _CLIENT_ID / _CLIENT_SECRET / _SUBSCRIPTION_ID (skip if --local-only)" ;;
        *ado*|*azure-devops*|*pipeline*)
            echo "check ADO_ORG / ADO_PROJECT / ADO_PAT in .env" ;;
        *slack*)
            echo "check the 'Slack account 4' credential in n8n UI + SLACK_CHANNEL_* in .env.n8n" ;;
        *openai*|*llm*|*ai*)
            echo "check the 'OpenAI account 4' credential in n8n UI (or the LLM key)" ;;
        *loganalytics*)
            echo "Log Analytics — Azure workspace + OAuth (skip if --local-only)" ;;
        *aipp*|*validate*|*init*trace*|*parse*|*normalize*)
            echo "AIPP-side node — inspect the exec JSON in n8n UI for the exact input shape" ;;
        *)
            echo "-" ;;
    esac
}

TOTAL=0; PASS=0; FAIL=0; WAIT=0; SKIP=0; NORUN=0
REPORT_CSV="/tmp/aipp-smoke-report.csv"
{ echo "STATUS,WORKFLOW,FIRE,HTTP,EXEC_ID,LAST_NODE,ERROR,FIX_HINT"; } > "$REPORT_CSV"

for f in "$WF_DIR"/*.json; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    name="${WF_NAME[$base]:-$base}"
    method="${FIRE_METHOD[$base]:-?}"
    http="${FIRE_HTTP[$base]:--}"
    wid="${WF_ID[$base]:-}"
    TOTAL=$((TOTAL+1))

    if [[ "$method" == "skipped-azure" ]]; then
        SKIP=$((SKIP+1))
        echo -e "  ${C_DIM}⊘ SKIP    ${C_R}${name} ${C_DIM}(Azure — needs credentials)${C_R}"
        echo "SKIP,\"$name\",skipped-azure,-,-,-,-,-" >> "$REPORT_CSV"; continue
    fi
    if [[ "$method" == "error-trigger (skipped)" ]]; then
        SKIP=$((SKIP+1))
        echo -e "  ${C_DIM}⊘ SKIP    ${C_R}${name} ${C_DIM}(error-trigger — only fires on other-flow errors)${C_R}"
        echo "SKIP,\"$name\",error-trigger,-,-,-,-,-" >> "$REPORT_CSV"; continue
    fi
    if [[ "$method" == "schedule (verify in n8n UI)" ]]; then
        SKIP=$((SKIP+1))
        echo -e "  ${C_DIM}⊘ SKIP    ${C_R}${name} ${C_DIM}(schedule — cannot trigger via API on n8n Community; check UI)${C_R}"
        echo "SKIP,\"$name\",schedule-manual,-,-,-,-,-" >> "$REPORT_CSV"; continue
    fi

    # Query executions FILTERED to this specific workflow — much more
    # reliable than the unfiltered list because schedule executions from
    # other workflows can push our webhook executions off the 250-row window.
    per_wf_json=$(curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
        --max-time 20 \
        "$BASE/api/v1/executions?workflowId=$wid&limit=3" 2>/dev/null || echo '{}')
    verdict=$(echo "$per_wf_json" | python3 -c "
import json,sys
try: d=json.loads(sys.stdin.read())
except Exception: print('NORUN|||'); raise SystemExit
execs=d.get('data') or []
if not execs: print('NORUN|||'); raise SystemExit
# Pick the newest (list is already sorted desc by n8n).
e=execs[0]
sf=(e.get('status') or '').lower()
fin=e.get('finished'); stop=e.get('stoppedAt'); wait=e.get('waitTill')
eid=str(e.get('id') or '-')
res=(e.get('data') or {}).get('resultData') or {}
run=res.get('runData') or {}
last=res.get('lastNodeExecuted') or '-'
err=res.get('error') or {}
msg=(err.get('message') or '').replace('|',' ').replace(chr(10),' ')[:150]
if sf=='waiting' or (fin is False and wait):
    v='WAIT'
elif sf=='error' or (fin is False and stop and not wait):
    v='FAIL'
    if last=='-' or last not in run:
        for k,runs in run.items():
            for r in runs or []:
                if isinstance(r,dict) and r.get('error'):
                    last=k; msg=msg or (r['error'].get('message') or '')[:150]; break
elif fin is True and sf in ('','success'): v='PASS'
elif sf=='running': v='WAIT'
else: v='FAIL'
print(f'{v}|{eid}|{last}|{msg}')")
    IFS='|' read -r v exec_id last_node err_msg <<< "$verdict"

    # If FAIL and we have no last-node info yet, fetch the full detail
    # for THIS execution (list endpoint on some n8n builds returns
    # metadata only). Best-effort — silently swallow errors.
    if [[ "$v" == "FAIL" && ( "$last_node" == "-" || -z "$last_node" ) && "$exec_id" != "-" ]]; then
        detail=$(curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
            --max-time 20 "$BASE/api/v1/executions/$exec_id?includeData=true" 2>/dev/null)
        extra=$(echo "$detail" | python3 -c "
import json,sys
try: e=json.loads(sys.stdin.read())
except Exception: print('|'); raise SystemExit
res=(e.get('data') or {}).get('resultData') or {}
run=res.get('runData') or {}
last=res.get('lastNodeExecuted') or '-'
err=res.get('error') or {}
msg=(err.get('message') or '').replace('|',' ').replace(chr(10),' ')[:150]
if last=='-' or last not in run:
    for k,runs in run.items():
        for r in runs or []:
            if isinstance(r,dict) and r.get('error'):
                last=k; msg=msg or (r['error'].get('message') or '')[:150]; break
print(f'{last}|{msg}')
")
        IFS='|' read -r last_node_new err_msg_new <<< "$extra"
        [[ -n "$last_node_new" && "$last_node_new" != "-" ]] && last_node="$last_node_new"
        [[ -n "$err_msg_new" ]] && err_msg="$err_msg_new"
    fi

    case "$v" in
        PASS)
            PASS=$((PASS+1))
            echo -e "  ${C_OK}✓ PASS    ${C_R}${name} ${C_DIM}exec=$exec_id${C_R}"
            echo "PASS,\"$name\",\"$method\",$http,$exec_id,\"$last_node\",\"$err_msg\",-" >> "$REPORT_CSV"
            ;;
        WAIT)
            WAIT=$((WAIT+1))
            echo -e "  ${C_WARN}⏸ WAIT    ${C_R}${name} ${C_DIM}exec=$exec_id (parked at HITL — click Approve/Reject in Slack)${C_R}"
            echo "WAIT,\"$name\",\"$method\",$http,$exec_id,\"$last_node\",\"$err_msg\",-" >> "$REPORT_CSV"
            ;;
        FAIL)
            FAIL=$((FAIL+1))
            hint=$(fix_hint "$last_node" "$err_msg")
            echo -e "  ${C_FAIL}✗ FAIL    ${C_R}${name} ${C_DIM}exec=$exec_id  last=${last_node}${C_R}"
            [[ -n "$err_msg" && "$err_msg" != "-" ]] && echo -e "        ${C_FAIL}└─ ${err_msg}${C_R}"
            [[ "$hint" != "-" ]] && echo -e "        ${C_INFO}└─ hint: ${hint}${C_R}"
            echo "FAIL,\"$name\",\"$method\",$http,$exec_id,\"$last_node\",\"$err_msg\",\"$hint\"" >> "$REPORT_CSV"
            ;;
        NORUN)
            NORUN=$((NORUN+1))
            echo -e "  ${C_WARN}∅ NO-RUN  ${C_R}${name} ${C_DIM}(trigger HTTP $http but no execution — is it active?)${C_R}"
            echo "NORUN,\"$name\",\"$method\",$http,-,-,-,-" >> "$REPORT_CSV"
            ;;
        *)
            echo -e "  ${C_FAIL}? UNKNOWN ${C_R}${name} ${C_DIM}$v${C_R}"
            echo "UNKNOWN,\"$name\",\"$method\",$http,-,-,-,-" >> "$REPORT_CSV"
            ;;
    esac
done

# =============================================================================
# STEP 4 — summary + AIPP proxy /health snapshot
# =============================================================================
echo ""
echo -e "${C_BOLD}══════════════════ Summary ══════════════════${C_R}"
echo -e "  Total     : $TOTAL"
echo -e "  ${C_OK}Passed    : $PASS${C_R}"
echo -e "  ${C_WARN}Waiting   : $WAIT${C_R}   ${C_DIM}(parked at HITL — expected)${C_R}"
echo -e "  ${C_FAIL}Failed    : $FAIL${C_R}"
echo -e "  ${C_DIM}Skipped   : $SKIP${C_R}"
echo -e "  ${C_WARN}No-run    : $NORUN${C_R}"
echo ""
echo -e "  Full CSV  : ${C_INFO}$REPORT_CSV${C_R}"

if [[ -n "${AIPP_BASE_URL:-}" && -n "${PROXY_API_KEY:-}" ]]; then
    echo ""
    echo -e "${C_BOLD}AIPP proxy /health${C_R}  (which local integrations AIPP thinks are configured)"
    curl -sS -H "Authorization: Bearer $PROXY_API_KEY" \
         --max-time 10 "${AIPP_BASE_URL%/}/api/proxy/health" \
         | python3 -m json.tool 2>/dev/null \
         || echo "  (could not reach $AIPP_BASE_URL/api/proxy/health)"
fi

echo ""
if [[ $FAIL -gt 0 || $NORUN -gt 0 ]]; then
    echo -e "${C_WARN}Some workflows need attention.${C_R}"
    echo -e "${C_DIM}Read the hints above and cross-reference with the /api/proxy/health output.${C_R}"
    exit 1
fi
echo -e "${C_OK}All fired workflows are green (or parked at HITL — expected).${C_R}"
