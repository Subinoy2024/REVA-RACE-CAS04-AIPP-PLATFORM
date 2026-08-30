#!/usr/bin/env bash
# ==============================================================================
# AIPP · n8n Non-Interactive Deploy Script
# ==============================================================================
# Use this when your .env.n8n secrets are ALREADY set (you rotated manually).
# It:
#   1. Backs up .env.n8n
#   2. Sanitizes syntax bugs in-place:
#        - Strips inline comments (e.g. `SLACK_SIGNING_SECRET= # blah`)
#        - Uncomments GITHUB_PAT / GH_ORG / GH_REPO lines if commented
#        - Removes deprecated keys (AZURE_TOKEN, AZURE_SUB, RG, LAW_ID,
#          IAC_REPO, IAC_REPO_PATH, ADO_PAT_B64, K8S_MODE, K8S_PROXY_URL)
#        - Fixes ADO_ORG=https://dev.azure.com/... -> just the slug
#        - Adds missing keys (SVCMAP, K8S_CA_VERIFY, GH_REPO_ALLOWLIST etc.)
#          only if they don't exist yet
#   3. Restarts the n8n container
#   4. Verifies env vars are loaded (masked)
#   5. Deploys the 16 workflows via REST API
#
# Safe to re-run. Never overwrites secrets you already set.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N8N_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$N8N_DIR/.env.n8n"
TS="$(date +%Y%m%d_%H%M%S)"

c_ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m⚠\033[0m %s\n' "$*"; }
c_err()  { printf '\033[31m✗\033[0m %s\n' "$*"; }
c_hdr()  { printf '\n\033[36m▶ %s\033[0m\n' "$*"; }

# ----------------------------------------------------------------------------
c_hdr "STEP 0 · Preconditions"
command -v docker  >/dev/null || { c_err "docker not found"; exit 1; }
command -v python3 >/dev/null || { c_err "python3 not found"; exit 1; }
[[ -f "$ENV_FILE" ]] || { c_err "$ENV_FILE not found"; exit 1; }
c_ok ".env.n8n present"

# ----------------------------------------------------------------------------
c_hdr "STEP 1 · Backup"
cp "$ENV_FILE" "${ENV_FILE}.bak.${TS}"
c_ok "Saved: ${ENV_FILE}.bak.${TS}"

# ----------------------------------------------------------------------------
c_hdr "STEP 2 · Sanitize .env.n8n"

python3 - "$ENV_FILE" <<'PY'
import re, sys, os
p = sys.argv[1]
raw = open(p).read().splitlines()

# ---- config ----------------------------------------------------------------
DEPRECATED   = {"AZURE_TOKEN","AZURE_SUB","RG","LAW_ID","IAC_REPO",
                "IAC_REPO_PATH","ADO_PAT_B64","K8S_MODE","K8S_PROXY_URL"}
UNCOMMENT_IF_HAS_VALUE = {"GITHUB_PAT","GH_ORG","GH_REPO","IAC_REPO_OWNER",
                          "IAC_REPO_NAME","GH_REPO_ALLOWLIST"}
REQUIRED_DEFAULTS = {
    "K8S_CA_VERIFY":                "false",
    "PROXMOX_VERIFY_SSL":           "false",
    "SLACK_CHANNEL_DEFAULT":        "aipp",
    "SLACK_CHANNEL_ALERTS":         "aipp",
    "SLACK_CHANNEL_APPROVALS":      "aipp",
    "SLACK_CHANNEL_DIGEST":         "aipp",
    "SLACK_SIGNING_SECRET":         "",
    "SVCMAP":                       '{"api-*":"backend-team","web-*":"frontend-team","payments-*":"platform"}',
    # keep Azure keys present but blank so gates evaluate cleanly
    "AZURE_TENANT_ID":              "",
    "AZURE_CLIENT_ID":              "",
    "AZURE_CLIENT_SECRET":          "",
    "AZURE_SUBSCRIPTION_ID":        "",
    "AZURE_RG_DEFAULT":             "",
    "AZURE_LOG_ANALYTICS_WORKSPACE_ID": "",
}

# ---- pass 1: parse -> {key: value}, preserving section comments -----------
kv = {}
out_lines = []
kv_line_re = re.compile(r'^\s*(#?\s*)([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$')

for line in raw:
    m = kv_line_re.match(line)
    if not m:
        out_lines.append(line)
        continue

    lead, key, val = m.groups()
    commented = lead.strip().startswith('#')
    # If the value is ONLY a comment (starts with #), treat as empty
    if val.lstrip().startswith('#'):
        val = ''
    # Strip inline comments only when value doesn't look like JSON
    elif val and not (val.lstrip().startswith('{') or val.lstrip().startswith('[')):
        # split on ' #' or '\t#' but NOT on '=#' (part of a value)
        val = re.split(r'\s+#', val, maxsplit=1)[0]
    val = val.strip().strip('"').strip("'")

    if key in DEPRECATED:
        continue                                    # drop entirely

    if commented:
        # Uncomment ONLY if:
        #  - key is in UNCOMMENT_IF_HAS_VALUE, AND
        #  - the commented value is non-empty AND non-placeholder
        placeholder_signals = ("PASTE", "REPLACE", "your-", "<", "REPLACE-WITH")
        if (key in UNCOMMENT_IF_HAS_VALUE
                and val
                and not any(s in val for s in placeholder_signals)):
            kv[key] = val                           # promote to real value
        # else: keep commented — just drop the line, we'll re-emit below
        continue

    kv[key] = val

# Fix ADO_ORG if it's still a URL
if "ADO_ORG" in kv:
    v = kv["ADO_ORG"]
    v = re.sub(r'^https?://dev\.azure\.com/', '', v).rstrip('/')
    kv["ADO_ORG"] = v

# Ensure all required keys exist (blank if not present)
for k, default in REQUIRED_DEFAULTS.items():
    kv.setdefault(k, default)

# ---- Emit a fresh, ordered file --------------------------------------------
SECTIONS = [
    ("### Kubernetes",
     ["K8S_API_URL","K8S_TOKEN","K8S_CA_VERIFY"]),
    ("### Grafana + Prometheus",
     ["GRAFANA_URL","GRAFANA_API_KEY","PROMETHEUS_URL"]),
    ("### Proxmox",
     ["PROXMOX_URL","PROXMOX_TOKEN","PROXMOX_NODE","PROXMOX_VERIFY_SSL"]),
    ("### Azure (SP blocked by REVA - workflows skip silently)",
     ["AZURE_TENANT_ID","AZURE_CLIENT_ID","AZURE_CLIENT_SECRET",
      "AZURE_SUBSCRIPTION_ID","AZURE_RG_DEFAULT","AZURE_LOG_ANALYTICS_WORKSPACE_ID"]),
    ("### GitHub",
     ["GITHUB_PAT","GH_ORG","GH_REPO","IAC_REPO_OWNER","IAC_REPO_NAME","GH_REPO_ALLOWLIST"]),
    ("### Azure DevOps",
     ["ADO_ORG","ADO_PROJECT","ADO_PAT"]),
    ("### Slack channels",
     ["SLACK_CHANNEL_DEFAULT","SLACK_CHANNEL_ALERTS","SLACK_CHANNEL_APPROVALS",
      "SLACK_CHANNEL_DIGEST","SLACK_SIGNING_SECRET"]),
    ("### Service-ownership map (used by #10 Incident Commander)",
     ["SVCMAP"]),
]

lines = ["# AIPP n8n runtime env - sanitized on the fly"]
for hdr, keys in SECTIONS:
    lines.append("")
    lines.append(hdr)
    for k in keys:
        lines.append(f"{k}={kv.get(k,'')}")

with open(p, "w") as f:
    f.write("\n".join(lines) + "\n")

os.chmod(p, 0o600)
print(f"OK - wrote {len(lines)} lines, {len(kv)} keys")
PY
c_ok "Sanitized (permissions: 0600)"

# ----------------------------------------------------------------------------
c_hdr "STEP 3 · Verify keys (masked)"
grep -E '^[A-Z_]+=' "$ENV_FILE" | \
    awk -F= '{print "  " $1 "=" (length($2) > 0 ? "***set***" : "empty")}' | \
    sort

# Fail hard if any of these critical keys are empty
CRITICAL="K8S_TOKEN GITHUB_PAT PROXMOX_TOKEN GRAFANA_API_KEY ADO_PAT"
MISSING=""
for k in $CRITICAL; do
    val="$(grep -E "^${k}=" "$ENV_FILE" | head -1 | cut -d= -f2-)"
    [[ -z "$val" ]] && MISSING="$MISSING $k"
done
if [[ -n "$MISSING" ]]; then
    c_err "Critical keys empty:$MISSING"
    echo "   Edit $ENV_FILE, fill values, then re-run."
    exit 2
fi
c_ok "All 5 critical secrets present"

# ----------------------------------------------------------------------------
c_hdr "STEP 4 · Restart n8n container"

N8N_CT="$(docker ps --format '{{.Names}}' | grep -i '^n8n' | head -1 || true)"
[[ -z "$N8N_CT" ]] && \
    N8N_CT="$(docker ps --filter 'ancestor=n8nio/n8n' --format '{{.Names}}' | head -1 || true)"

if [[ -z "$N8N_CT" ]]; then
    c_warn "n8n container not auto-detected."
    read -r -p "Enter n8n container name manually (or blank to skip restart): " N8N_CT
fi

if [[ -n "$N8N_CT" ]]; then
    c_ok "Container: $N8N_CT"
    docker restart "$N8N_CT" >/dev/null
    echo "   Waiting 15s for n8n to boot..."
    sleep 15
    c_ok "n8n restarted"

    c_hdr "STEP 5 · Verify env vars inside n8n"
    docker exec "$N8N_CT" sh -c 'env' 2>/dev/null | \
        grep -E '^(K8S_|GITHUB_|GH_|SVCMAP|ADO_|SLACK_CHANNEL_|PROXMOX_|GRAFANA_|IAC_REPO_|SLACK_SIGNING)' | \
        awk -F= '{print "  " $1 "=" (length($2) > 0 ? "***set***" : "empty")}' | \
        sort
else
    c_warn "Skipping restart. Env vars will only load after you restart n8n manually."
fi

# ----------------------------------------------------------------------------
c_hdr "STEP 6 · Deploy 16 workflows via n8n REST API"

if [[ ! -f "$SCRIPT_DIR/deploy.sh" ]]; then
    c_err "deploy.sh not found in $SCRIPT_DIR"; exit 1
fi
bash "$SCRIPT_DIR/deploy.sh"

# ----------------------------------------------------------------------------
c_hdr "🎉 Done"
cat <<EOF

Smoke-test workflow #07 (K8s Troubleshoot):

  POD=\$(kubectl get pods -n default -o name | head -1 | cut -d/ -f2)
  curl -X POST 'https://n8n.dccloud.in.net/webhook/aipp-troubleshoot' \\
    -H 'Content-Type: application/json' \\
    -d "{\"body\":{\"text\":\"pod=\$POD ns=default\"}}"

Then open the n8n UI → Executions to watch it run, and check #aipp in Slack.

Backup of previous .env.n8n: ${ENV_FILE}.bak.${TS}
EOF
