#!/usr/bin/env bash
# ==============================================================================
# AIPP · n8n One-Shot Setup Script
# ==============================================================================
# What it does (in order):
#   1. Backs up the current .env.n8n → .env.n8n.bak.<timestamp>
#   2. Rotates the Kubernetes ServiceAccount token via kubectl (automatic)
#   3. Prompts you for the 4 tokens that must be rotated in web UIs
#      (Grafana, Proxmox, GitHub PAT, ADO PAT) — with clear links
#   4. Writes a clean, correct .env.n8n
#   5. Auto-detects your n8n container and restarts it
#   6. Verifies env vars are loaded inside n8n
#   7. Runs scripts/deploy.sh to push all 16 workflows
#
# Idempotent: safe to run multiple times. Uses your existing values as defaults
# whenever possible.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N8N_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$N8N_DIR/.env.n8n"
TS="$(date +%Y%m%d_%H%M%S)"

# -- helpers -------------------------------------------------------------------
c_ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m⚠\033[0m %s\n' "$*"; }
c_err()  { printf '\033[31m✗\033[0m %s\n' "$*"; }
c_hdr()  { printf '\n\033[36m▶ %s\033[0m\n' "$*"; }

read_default() {
    # read_default PROMPT DEFAULT_VALUE -> echoes user's input or default
    local prompt="$1" default="${2:-}" ans
    if [[ -n "$default" ]]; then
        read -r -p "$prompt [current: kept] : " ans
        ans="${ans:-$default}"
    else
        read -r -p "$prompt : " ans
    fi
    printf '%s' "$ans"
}

read_secret() {
    # read_secret PROMPT DEFAULT_VALUE -> like read_default but hides input
    local prompt="$1" default="${2:-}" ans
    if [[ -n "$default" ]]; then
        read -r -s -p "$prompt [current: kept, press Enter to reuse] : " ans; echo
        ans="${ans:-$default}"
    else
        read -r -s -p "$prompt : " ans; echo
    fi
    printf '%s' "$ans"
}

extract() {
    # extract KEY  -> value from current .env.n8n (empty if missing/commented)
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true
}

# ==============================================================================
# STEP 0 — Preconditions
# ==============================================================================
c_hdr "STEP 0 · Preconditions"

command -v kubectl >/dev/null   || { c_err "kubectl not found"; exit 1; }
command -v docker  >/dev/null   || { c_err "docker not found";  exit 1; }
command -v curl    >/dev/null   || { c_err "curl not found";    exit 1; }
command -v python3 >/dev/null   || { c_err "python3 not found"; exit 1; }

[[ -f "$ENV_FILE" ]] || { c_err "$ENV_FILE not found"; exit 1; }
c_ok "All required tools present · $ENV_FILE exists"

# ==============================================================================
# STEP 1 — Backup
# ==============================================================================
c_hdr "STEP 1 · Backing up current .env.n8n"
cp "$ENV_FILE" "${ENV_FILE}.bak.${TS}"
c_ok "Backup written to ${ENV_FILE}.bak.${TS}"

# ==============================================================================
# STEP 2 — Rotate Kubernetes token automatically
# ==============================================================================
c_hdr "STEP 2 · Rotating Kubernetes ServiceAccount token"

K8S_SA_NAME="${K8S_SA_NAME:-n8n-reader}"
K8S_SA_NS="${K8S_SA_NS:-default}"

if kubectl get sa "$K8S_SA_NAME" -n "$K8S_SA_NS" >/dev/null 2>&1; then
    c_ok "ServiceAccount ${K8S_SA_NS}/${K8S_SA_NAME} exists — reusing"
else
    c_warn "ServiceAccount ${K8S_SA_NS}/${K8S_SA_NAME} missing — creating"
    kubectl create sa "$K8S_SA_NAME" -n "$K8S_SA_NS"
    kubectl create clusterrolebinding "n8n-reader-view" \
        --clusterrole=view --serviceaccount="${K8S_SA_NS}:${K8S_SA_NAME}" \
        2>/dev/null || true
    c_ok "Created SA + ClusterRoleBinding"
fi

echo "   Issuing a fresh 1-year token…"
NEW_K8S_TOKEN="$(kubectl create token "$K8S_SA_NAME" -n "$K8S_SA_NS" --duration=8760h)"
c_ok "New K8s token issued (length: ${#NEW_K8S_TOKEN})"

K8S_API_URL_CURRENT="$(extract K8S_API_URL)"
K8S_API_URL_CURRENT="${K8S_API_URL_CURRENT:-https://192.168.88.22:6443}"

# ==============================================================================
# STEP 3 — Prompt for tokens that must be rotated in web UIs
# ==============================================================================
c_hdr "STEP 3 · Manual rotation of Grafana / Proxmox / GitHub / ADO tokens"

cat <<'EOF'
Before proceeding, rotate these 4 tokens in their respective web UIs:

  1. Grafana  → Administration → Service accounts → n8n → delete & recreate token
  2. Proxmox  → Datacenter → Permissions → API Tokens → root@pam!n8n → delete & recreate
  3. GitHub   → https://github.com/settings/personal-access-tokens → revoke leaked, create new
  4. ADO      → dev.azure.com → avatar → Personal Access Tokens → revoke & recreate

You can paste the NEW values below. Press Enter to reuse the existing value
(only useful if that particular token was NOT leaked).

EOF

# Grafana
GRAFANA_URL_CURRENT="$(extract GRAFANA_URL)"
GRAFANA_URL_CURRENT="${GRAFANA_URL_CURRENT:-https://grafana.dccloud.in.net}"
GRAFANA_URL="$(read_default 'Grafana URL' "$GRAFANA_URL_CURRENT")"
GRAFANA_API_KEY_CURRENT="$(extract GRAFANA_API_KEY)"
GRAFANA_API_KEY="$(read_secret 'New Grafana API key (glsa_...)' "$GRAFANA_API_KEY_CURRENT")"

# Prometheus
PROMETHEUS_URL_CURRENT="$(extract PROMETHEUS_URL)"
PROMETHEUS_URL_CURRENT="${PROMETHEUS_URL_CURRENT:-http://prometheus.dccloud.com}"
PROMETHEUS_URL="$(read_default 'Prometheus URL' "$PROMETHEUS_URL_CURRENT")"

# Proxmox
PROXMOX_URL_CURRENT="$(extract PROXMOX_URL)"
PROXMOX_URL_CURRENT="${PROXMOX_URL_CURRENT:-https://bharat.dccloud.in.net:8006}"
PROXMOX_URL="$(read_default 'Proxmox URL' "$PROXMOX_URL_CURRENT")"
PROXMOX_TOKEN_CURRENT="$(extract PROXMOX_TOKEN)"
PROXMOX_TOKEN="$(read_secret 'New Proxmox token (root@pam!n8n=UUID)' "$PROXMOX_TOKEN_CURRENT")"
PROXMOX_NODE_CURRENT="$(extract PROXMOX_NODE)"
PROXMOX_NODE_CURRENT="${PROXMOX_NODE_CURRENT:-pve2}"
PROXMOX_NODE="$(read_default 'Proxmox node' "$PROXMOX_NODE_CURRENT")"

# GitHub
GITHUB_PAT="$(read_secret 'New GitHub fine-grained PAT (github_pat_...)' '')"
GH_ORG_CURRENT="$(extract GH_ORG)"
GH_ORG_CURRENT="${GH_ORG_CURRENT:-Subinoy2024}"
GH_ORG="$(read_default 'GitHub org / owner' "$GH_ORG_CURRENT")"
GH_REPO_CURRENT="$(extract GH_REPO)"
GH_REPO_CURRENT="${GH_REPO_CURRENT:-AIPP-AI-Driven-Pipeline-Platform-RACE}"
GH_REPO="$(read_default 'GitHub main repo name (no owner)' "$GH_REPO_CURRENT")"

# ADO
ADO_ORG_RAW="$(read_default 'ADO org SLUG (just the name, no https://)' '')"
# scrub any pasted URL prefix
ADO_ORG="${ADO_ORG_RAW#https://dev.azure.com/}"; ADO_ORG="${ADO_ORG%/}"
ADO_PROJECT_CURRENT="$(extract ADO_PROJECT)"
ADO_PROJECT_CURRENT="${ADO_PROJECT_CURRENT:-DC-CLOUD-SERVICE}"
ADO_PROJECT="$(read_default 'ADO project' "$ADO_PROJECT_CURRENT")"
ADO_PAT="$(read_secret 'New ADO PAT' '')"

# ==============================================================================
# STEP 4 — Write the new .env.n8n
# ==============================================================================
c_hdr "STEP 4 · Writing new .env.n8n"

cat > "$ENV_FILE" <<EOF
# AIPP n8n runtime env - regenerated $(date -u +%Y-%m-%dT%H:%M:%SZ)
# DO NOT commit this file. Rotated by scripts/setup_env_and_deploy.sh

### Kubernetes
K8S_API_URL=${K8S_API_URL_CURRENT}
K8S_TOKEN=${NEW_K8S_TOKEN}
K8S_CA_VERIFY=false

### Grafana + Prometheus
GRAFANA_URL=${GRAFANA_URL}
GRAFANA_API_KEY=${GRAFANA_API_KEY}
PROMETHEUS_URL=${PROMETHEUS_URL}

### Proxmox
PROXMOX_URL=${PROXMOX_URL}
PROXMOX_TOKEN=${PROXMOX_TOKEN}
PROXMOX_NODE=${PROXMOX_NODE}
PROXMOX_VERIFY_SSL=false

### Azure (SP blocked by REVA tenant - skipped, workflows exit silently)
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
AZURE_SUBSCRIPTION_ID=
AZURE_RG_DEFAULT=
AZURE_LOG_ANALYTICS_WORKSPACE_ID=

### GitHub
GITHUB_PAT=${GITHUB_PAT}
GH_ORG=${GH_ORG}
GH_REPO=${GH_REPO}
IAC_REPO_OWNER=${GH_ORG}
IAC_REPO_NAME=${GH_REPO}
GH_REPO_ALLOWLIST=${GH_ORG}/${GH_REPO}

### Azure DevOps
ADO_ORG=${ADO_ORG}
ADO_PROJECT=${ADO_PROJECT}
ADO_PAT=${ADO_PAT}

### Slack channels
SLACK_CHANNEL_DEFAULT=aipp
SLACK_CHANNEL_ALERTS=aipp
SLACK_CHANNEL_APPROVALS=aipp
SLACK_CHANNEL_DIGEST=aipp
SLACK_SIGNING_SECRET=

### Service-ownership map (for #10 Incident Commander)
SVCMAP={"api-*":"backend-team","web-*":"frontend-team","payments-*":"platform"}
EOF
chmod 600 "$ENV_FILE"
c_ok "$ENV_FILE written (0600 perms)"

# ==============================================================================
# STEP 5 — Restart n8n container
# ==============================================================================
c_hdr "STEP 5 · Restarting n8n container"

N8N_CT="$(docker ps --format '{{.Names}}' | grep -i '^n8n' | head -1 || true)"
if [[ -z "$N8N_CT" ]]; then
    N8N_CT="$(docker ps --filter 'ancestor=n8nio/n8n' --format '{{.Names}}' | head -1 || true)"
fi

if [[ -z "$N8N_CT" ]]; then
    c_warn "Could not auto-detect n8n container. Skipping restart."
    c_warn "Restart manually: docker restart <your-n8n-container-name>"
else
    c_ok "Detected n8n container: $N8N_CT"
    echo "   Restarting..."
    docker restart "$N8N_CT" >/dev/null
    echo "   Waiting 15s for n8n to boot..."
    sleep 15
    c_ok "n8n restarted"
fi

# ==============================================================================
# STEP 6 — Verify env vars inside n8n
# ==============================================================================
c_hdr "STEP 6 · Verifying env vars inside n8n container"

if [[ -n "$N8N_CT" ]]; then
    echo "   Checking critical vars..."
    docker exec "$N8N_CT" sh -c 'env' 2>/dev/null | \
        grep -E '^(K8S_|GITHUB_|GH_|SVCMAP|ADO_|SLACK_CHANNEL_|PROXMOX_|GRAFANA_|IAC_REPO_)' | \
        awk -F= '{print "  " $1 "=" (length($2) > 0 ? "***set***" : "empty")}' | \
        sort
    echo ""
    MISSING="$(docker exec "$N8N_CT" sh -c 'env' 2>/dev/null | \
        grep -cE '^(K8S_TOKEN|GITHUB_PAT|ADO_PAT|PROXMOX_TOKEN|GRAFANA_API_KEY)=..' || true)"
    if [[ "$MISSING" -ge 5 ]]; then
        c_ok "All 5 critical secrets loaded"
    else
        c_warn "Only $MISSING/5 critical secrets loaded — check n8n mount config"
    fi
fi

# ==============================================================================
# STEP 7 — Deploy the 16 workflows
# ==============================================================================
c_hdr "STEP 7 · Deploying workflows via n8n REST API"

if [[ ! -f "$SCRIPT_DIR/deploy.sh" ]]; then
    c_err "deploy.sh not found in $SCRIPT_DIR"; exit 1
fi
bash "$SCRIPT_DIR/deploy.sh"

# ==============================================================================
# Done
# ==============================================================================
c_hdr "🎉 Done"
cat <<EOF

Next: smoke-test workflow #07 (K8s Troubleshoot)

   POD=\$(kubectl get pods -n default -o name | head -1 | cut -d/ -f2)
   curl -X POST 'https://n8n.dccloud.in.net/webhook/aipp-troubleshoot' \\
     -H 'Content-Type: application/json' \\
     -d "{\"body\":{\"text\":\"pod=\$POD ns=default\"}}"

Then open n8n UI → Executions to watch the flow end-to-end and check #aipp
Slack for the diagnosis card.

Backup of previous .env.n8n: ${ENV_FILE}.bak.${TS}
EOF
