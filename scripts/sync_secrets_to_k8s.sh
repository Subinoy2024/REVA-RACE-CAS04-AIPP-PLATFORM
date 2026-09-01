#!/usr/bin/env bash
# ==============================================================================
# AIPP · One-Click Local .env to Kubernetes Secret Sync & Auto-Restart
# ==============================================================================
# Whenever you update .env (e.g. OpenAI key, tokens, database passwords),
# run this script to instantly sync credentials to the live K8s cluster
# and gracefully reload the backend without downtime.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="${SCRIPT_DIR}/.."
ENV_FILE="${ROOT_DIR}/.env"
SECRET_YAML="${ROOT_DIR}/k8s/secret.yaml"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ Error: .env file not found at $ENV_FILE"
    exit 1
fi

echo "=================================================================="
echo " 🔄 AIPP Credential Sync: Local .env ──► Kubernetes (aipp)"
echo "=================================================================="

# 1. Parse LLM keys from .env
OPENAI_KEY=$(grep -E "^OPENAI_API_KEY=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'" | tr -d '\r' | xargs || true)
AIPP_KEY=$(grep -E "^AIPP_LLM_KEY=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'" | tr -d '\r' | xargs || true)

if [[ -z "$OPENAI_KEY" && -z "$AIPP_KEY" ]]; then
    echo "⚠️ Warning: No OPENAI_API_KEY or AIPP_LLM_KEY found in .env"
fi

# 2. Update k8s/secret.yaml safely
echo "→ Synchronizing k8s/secret.yaml..."
python3 -c "
import re

env_file = '$ENV_FILE'
secret_file = '$SECRET_YAML'

# Read .env
env_vars = {}
with open(env_file, 'r') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env_vars[k.strip()] = v.strip().strip('\"').strip('\'')

# Update secret.yaml for critical rotating keys
with open(secret_file, 'r') as f:
    content = f.read()

for key in ['OPENAI_API_KEY', 'AIPP_LLM_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'JWT_SECRET', 'N8N_API_KEY', 'PROXY_API_KEY', 'GITHUB_PAT', 'ADO_PAT']:
    if key in env_vars:
        val = env_vars[key]
        # Replace stringData key
        content = re.sub(rf'({key}:\s*\").*?(\")', rf'\g<1>{val}\g<2>', content)

with open(secret_file, 'w') as f:
    f.write(content)
"

# 3. Apply to Kubernetes cluster
echo "→ Applying secret to Kubernetes namespace 'aipp'..."
kubectl apply -f "$SECRET_YAML"

# 4. Gracefully restart backend deployment
echo "→ Performing rolling restart of aipp-backend..."
kubectl rollout restart deployment/aipp-backend -n aipp

echo "→ Waiting for healthy rollout..."
kubectl rollout status deployment/aipp-backend -n aipp --timeout=60s

echo "=================================================================="
echo " ✅ Sync Complete! Backend is running with the latest credentials."
echo "=================================================================="
