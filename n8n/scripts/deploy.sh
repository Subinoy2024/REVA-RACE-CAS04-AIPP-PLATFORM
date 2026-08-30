#!/usr/bin/env bash
# ==============================================================================
# AIPP · n8n Workflow Deployer
# ==============================================================================
#
# Pushes all workflow JSON files in ../workflows/*.json to an n8n instance
# using the n8n REST API. Idempotent — reruns update existing workflows.
#
# ------------------------------------------------------------------------------
# Modes:
#   1. API mode (default)  — uses N8N_BASE_URL + N8N_API_KEY over HTTPS.
#   2. SSH mode            — SCP JSONs to the remote n8n host, then run
#                            `n8n import:workflow --input=/tmp/*.json` on it.
#                            Use when the n8n API is not reachable from the
#                            AIPP app server but SSH is.
#
# ------------------------------------------------------------------------------
# Env vars (read from ../. env if present, otherwise the shell):
#   N8N_BASE_URL      — required for API mode      (e.g. https://n8n.dccloud.in.net)
#   N8N_API_KEY       — required for API mode      (JWT from n8n Settings → API)
#   N8N_SSH_HOST      — required for SSH mode      (e.g. vmadmin@n8n-host)
#   N8N_SSH_KEY       — optional path to SSH key   (default: ~/.ssh/id_rsa)
#   N8N_CLI_PATH      — optional path to n8n binary (default: n8n)
#
# ------------------------------------------------------------------------------
# Usage:
#   ./deploy.sh                    # API mode (default)
#   ./deploy.sh --ssh              # SSH mode
#   ./deploy.sh --dry-run          # list what WOULD be pushed
#   ./deploy.sh --activate         # activate just the workflows pushed this run
#   ./deploy.sh --activate-all     # activate every workflow on the server after push
#   ./deploy.sh --file 01_*.json   # push a single file
# ==============================================================================

set -euo pipefail

# Cloudflare in front of some n8n deployments blocks default curl UA (error 1010).
# Send a real browser UA on every request.
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 AIPP-Deploy"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WORKFLOWS_DIR="${SCRIPT_DIR}/../workflows"
ENV_FILE="${SCRIPT_DIR}/../../.env"

# ---- pull env from AIPP's .env if present -----------------------------------
# Safe parser: only extracts KEY=VALUE lines, ignores comments/blank/quoted
# strings, and never evaluates bash on the value. Prevents crashes when a
# value contains &, <, >, |, backticks, or JSON.
if [[ -f "$ENV_FILE" ]]; then
    while IFS='=' read -r key val; do
        # Skip comments, blank lines, and malformed lines
        [[ -z "$key" ]] && continue
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] && continue
        # Strip surrounding quotes (single or double) from the value
        val="${val%$'\r'}"                     # windows CRLF
        val="${val#\"}"; val="${val%\"}"
        val="${val#\'}"; val="${val%\'}"
        # Only set if not already set in the environment
        if [[ -z "${!key:-}" ]]; then
            export "$key=$val"
        fi
    done < "$ENV_FILE"
fi

MODE="api"
DRY_RUN=0
ACTIVATE=0
ACTIVATE_ALL=0
SINGLE_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ssh)           MODE="ssh"; shift ;;
        --dry-run)       DRY_RUN=1; shift ;;
        --activate)      ACTIVATE=1; shift ;;
        --activate-all)  ACTIVATE_ALL=1; ACTIVATE=1; shift ;;
        --file)          SINGLE_FILE="$2"; shift 2 ;;
        -h|--help)       sed -n '2,32p' "$0"; exit 0 ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
    esac
done

# ---- auto-rebuild workflows if .env.n8n is newer than any JSON -------------
BUILD_SCRIPT="$SCRIPT_DIR/../build_workflows.py"
ENV_N8N="$SCRIPT_DIR/../.env.n8n"
if [[ -f "$BUILD_SCRIPT" && -f "$ENV_N8N" ]]; then
    latest_json=$(find "$WORKFLOWS_DIR" -maxdepth 1 -name '*.json' -printf '%T@\n' 2>/dev/null | sort -n | tail -1 || echo 0)
    env_mtime=$(stat -c %Y "$ENV_N8N" 2>/dev/null || echo 0)
    if [[ -z "$latest_json" ]] || (( ${env_mtime%.*} > ${latest_json%.*} )); then
        echo "→ .env.n8n changed since last build — regenerating workflows"
        python3 "$BUILD_SCRIPT"
        echo ""
    fi
fi

# ---- collect workflow files -------------------------------------------------
if [[ -n "$SINGLE_FILE" ]]; then
    FILES=( "$WORKFLOWS_DIR/$SINGLE_FILE" )
else
    FILES=( "$WORKFLOWS_DIR"/*.json )
fi


if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "❌ No workflow JSONs found in $WORKFLOWS_DIR — run build_workflows.py first."
    exit 1
fi

echo "=================================================================="
echo " AIPP · n8n Deployer · mode=$MODE · files=${#FILES[@]}"
if [[ "$MODE" == "api" ]]; then
    echo " Target: ${N8N_BASE_URL:-<UNSET>}"
elif [[ "$MODE" == "ssh" ]]; then
    echo " Target: ${N8N_SSH_HOST:-<UNSET>}"
fi
echo "=================================================================="

if [[ $DRY_RUN -eq 1 ]]; then
    echo ""
    echo "DRY RUN — would push:"
    for f in "${FILES[@]}"; do
        name=$(python3 -c "import json,sys; print(json.load(open('$f'))['name'])")
        echo "  • $(basename "$f")  →  $name"
    done
    exit 0
fi

# ---- validate creds ---------------------------------------------------------
if [[ "$MODE" == "api" ]]; then
    : "${N8N_BASE_URL:?N8N_BASE_URL is not set}"
    : "${N8N_API_KEY:?N8N_API_KEY is not set}"
    N8N_BASE_URL="${N8N_BASE_URL%/}"        # strip trailing slash
elif [[ "$MODE" == "ssh" ]]; then
    : "${N8N_SSH_HOST:?N8N_SSH_HOST is not set (e.g. vmadmin@n8n-host)}"
    N8N_SSH_KEY="${N8N_SSH_KEY:-$HOME/.ssh/id_rsa}"
    N8N_CLI_PATH="${N8N_CLI_PATH:-n8n}"
fi

# =============================================================================
# API MODE — n8n REST API upsert
# =============================================================================
api_push() {
    local file="$1"
    local name
    name=$(python3 -c "import json; print(json.load(open('$file'))['name'])")

    # Check if a workflow with this name already exists
    local existing_id
    existing_id=$(curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
        "$N8N_BASE_URL/api/v1/workflows?limit=250" \
        | python3 -c "
import json, sys
d = json.load(sys.stdin)
wfs = d.get('data') or d if isinstance(d, list) else d.get('data', [])
match = [w for w in wfs if w.get('name') == '''$name''']
print(match[0]['id'] if match else '')")

    # n8n's POST expects a subset of fields — strip the ones the API rejects.
    local sanitized
    sanitized=$(python3 -c "
import json, sys
d = json.load(open('$file'))
# n8n API rejects these on POST/PUT
for k in ('active', 'versionId', 'meta', 'staticData', 'pinData', 'tags'):
    d.pop(k, None)
print(json.dumps(d))")

    if [[ -n "$existing_id" ]]; then
        # Check if the workflow is currently active — n8n PUT resets it, so
        # we'll re-activate afterwards to preserve state across deploys.
        local was_active
        was_active=$(curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
            "$N8N_BASE_URL/api/v1/workflows/$existing_id" | \
            python3 -c "import json,sys; print(json.load(sys.stdin).get('active', False))" 2>/dev/null || echo "False")

        echo "  ↻ Updating $name (id=$existing_id)"
        response=$(curl -sS -X PUT -A "$UA" \
            -H "X-N8N-API-KEY: $N8N_API_KEY" \
            -H "Content-Type: application/json" \
            -d "$sanitized" \
            "$N8N_BASE_URL/api/v1/workflows/$existing_id")

        # Re-activate if it was active before the PUT clobbered its state.
        if [[ "$was_active" == "True" ]]; then
            curl -sS -X POST -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
                "$N8N_BASE_URL/api/v1/workflows/$existing_id/activate" > /dev/null || true
            echo "     ↺ re-activated (was active before update)"
        fi
    else
        echo "  + Creating $name"
        response=$(curl -sS -X POST -A "$UA" \
            -H "X-N8N-API-KEY: $N8N_API_KEY" \
            -H "Content-Type: application/json" \
            -d "$sanitized" \
            "$N8N_BASE_URL/api/v1/workflows")
    fi

    local new_id
    new_id=$(echo "$response" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('id') or d.get('data', {}).get('id', ''))
except Exception:
    print('')
")
    if [[ -z "$new_id" ]]; then
        echo "  ❌ Failed:"
        echo "$response" | head -c 300
        echo ""
        return 1
    fi

    if [[ $ACTIVATE -eq 1 ]]; then
        curl -sS -X POST -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
            "$N8N_BASE_URL/api/v1/workflows/$new_id/activate" > /dev/null || true
        echo "     ✓ activated"
    fi
}

# =============================================================================
# SSH MODE — scp + n8n CLI import
# =============================================================================
ssh_push() {
    local file="$1"
    local base
    base=$(basename "$file")
    echo "  ↑ scp $base → $N8N_SSH_HOST:/tmp/$base"
    scp -i "$N8N_SSH_KEY" -o StrictHostKeyChecking=accept-new \
        "$file" "$N8N_SSH_HOST:/tmp/$base" > /dev/null
    ssh -i "$N8N_SSH_KEY" -o StrictHostKeyChecking=accept-new "$N8N_SSH_HOST" \
        "$N8N_CLI_PATH import:workflow --input=/tmp/$base" \
        || echo "  ⚠ import returned non-zero (may still be OK — check n8n UI)"
    ssh -i "$N8N_SSH_KEY" "$N8N_SSH_HOST" "rm -f /tmp/$base" || true
}

# ---- main loop --------------------------------------------------------------
FAILED=0
for f in "${FILES[@]}"; do
    if [[ "$MODE" == "api" ]]; then
        api_push "$f" || FAILED=$((FAILED+1))
    else
        ssh_push "$f" || FAILED=$((FAILED+1))
    fi
done

echo ""
echo "=================================================================="
echo " Done. ${#FILES[@]} pushed · $FAILED failures"
echo "=================================================================="

# ---- optional bulk-activate every workflow on the server -------------------
# Useful right after a fresh deploy: flip every workflow (not just the ones
# pushed this run) to active so demo webhooks are all live in one command.
if [[ $ACTIVATE_ALL -eq 1 && "$MODE" == "api" ]]; then
    echo ""
    echo "→ --activate-all: flipping every workflow on the server to active"
    ALL_IDS=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && ALL_IDS+=("$line")
    done < <(curl -sS -A "$UA" -H "X-N8N-API-KEY: $N8N_API_KEY" \
        "$N8N_BASE_URL/api/v1/workflows?limit=250" | \
        python3 -c "
import json, sys
d = json.load(sys.stdin)
wfs = d.get('data') or d if isinstance(d, list) else d.get('data', [])
for w in wfs:
    print(f\"{w.get('id')}\t{w.get('name','')}\t{w.get('active', False)}\")")
    ACT_OK=0
    ACT_SKIP=0
    ACT_FAIL=0
    for row in "${ALL_IDS[@]}"; do
        wid="${row%%$'\t'*}"
        rest="${row#*$'\t'}"
        wname="${rest%%$'\t'*}"
        wactive="${rest##*$'\t'}"
        if [[ "$wactive" == "True" ]]; then
            ACT_SKIP=$((ACT_SKIP+1))
            continue
        fi
        code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST -A "$UA" \
            -H "X-N8N-API-KEY: $N8N_API_KEY" \
            "$N8N_BASE_URL/api/v1/workflows/$wid/activate" || echo "000")
        if [[ "$code" == "200" ]]; then
            echo "    ✓ activated: $wname"
            ACT_OK=$((ACT_OK+1))
        else
            echo "    ✗ HTTP $code  · $wname"
            ACT_FAIL=$((ACT_FAIL+1))
        fi
    done
    echo ""
    echo "  activate-all summary: activated=$ACT_OK · already-active=$ACT_SKIP · failed=$ACT_FAIL"
fi

[[ $FAILED -eq 0 ]] || exit 1
