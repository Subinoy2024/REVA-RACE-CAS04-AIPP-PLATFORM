#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# scripts/migrate_env.sh
#
# One-shot idempotent migrator for the AIPP `.env` file.
#
# What it does (only if needed — every step is safe to re-run):
#   1. Creates `.env` from `.env.example` if it doesn't exist.
#   2. Backs up the current `.env` to `.env.bak-<timestamp>` before touching it.
#   3. Renames legacy `EMERGENT_LLM_KEY` -> `AIPP_LLM_KEY` (preserves value).
#   4. Adds any keys the running codebase expects but the file is missing.
#   5. Generates a fresh `JWT_SECRET` and `AIPP_FERNET_KEY` ONLY if empty.
#   6. Prints a summary of what changed.
#
# Usage:
#   bash scripts/migrate_env.sh
# ---------------------------------------------------------------------------

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
EXAMPLE_FILE="$ROOT_DIR/.env.example"

BLUE="\033[1;36m"; GREEN="\033[1;32m"; YELLOW="\033[1;33m"; RED="\033[1;31m"; RESET="\033[0m"
info()  { printf "${BLUE}[migrate-env]${RESET} %s\n" "$*"; }
ok()    { printf "${GREEN}[migrate-env] ✔${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[migrate-env] ⚠${RESET} %s\n" "$*"; }
fail()  { printf "${RED}[migrate-env] ✗${RESET} %s\n" "$*" >&2; exit 1; }

# ---------- prerequisites --------------------------------------------------
command -v python3 >/dev/null 2>&1 || fail "python3 is required."
[[ -f "$EXAMPLE_FILE" ]] || fail "Missing $EXAMPLE_FILE — run from the repo root."

# ---------- 1. bootstrap .env if missing -----------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$EXAMPLE_FILE" "$ENV_FILE"
    ok "Created $ENV_FILE from .env.example"
fi

# ---------- 2. always back up first ----------------------------------------
STAMP=$(date +%Y%m%d-%H%M%S)
cp "$ENV_FILE" "$ENV_FILE.bak-$STAMP"
info "Backup written to $ENV_FILE.bak-$STAMP"

# ---------- helper: does KEY exist in .env? -------------------------------
has_key() {
    grep -E "^${1}=" "$ENV_FILE" >/dev/null 2>&1
}
# helper: read current value of a key (empty string if missing/blank)
val_of() {
    grep -E "^${1}=" "$ENV_FILE" | head -1 | cut -d= -f2- || echo ""
}
# helper: set/replace KEY=VALUE (safely handles slashes etc.)
set_key() {
    local key="$1" val="$2" tmp
    tmp="$(mktemp)"
    if has_key "$key"; then
        awk -v k="$key" -v v="$val" '
            BEGIN { done=0 }
            $0 ~ "^"k"=" && !done { print k"="v; done=1; next }
            { print }
        ' "$ENV_FILE" > "$tmp"
    else
        cat "$ENV_FILE" > "$tmp"
        printf "\n# added by migrate_env.sh on %s\n%s=%s\n" \
               "$(date -Iseconds)" "$key" "$val" >> "$tmp"
    fi
    mv "$tmp" "$ENV_FILE"
}

# ---------- 3. rename EMERGENT_LLM_KEY -> AIPP_LLM_KEY ---------------------
if has_key "EMERGENT_LLM_KEY"; then
    legacy="$(val_of EMERGENT_LLM_KEY)"
    current_new="$(val_of AIPP_LLM_KEY || true)"
    if [[ -z "$current_new" && -n "$legacy" ]]; then
        set_key "AIPP_LLM_KEY" "$legacy"
        ok "Migrated EMERGENT_LLM_KEY value -> AIPP_LLM_KEY"
    fi
    # comment-out (don't delete) so users can see the migration happened.
    sed -i.tmp -E "s/^EMERGENT_LLM_KEY=/# (migrated) EMERGENT_LLM_KEY=/" "$ENV_FILE"
    rm -f "$ENV_FILE.tmp"
    ok "Commented out legacy EMERGENT_LLM_KEY line"
elif ! has_key "AIPP_LLM_KEY"; then
    set_key "AIPP_LLM_KEY" ""
    warn "Added empty AIPP_LLM_KEY — remember to paste your key before starting"
fi

# ---------- 4. ensure every required key exists ----------------------------
# Only ADD if missing — never overwrite non-empty values.
declare -a REQUIRED_EMPTY_OK=(
    "POSTGRES_USER=aipp"
    "POSTGRES_PASSWORD=aipp_local"
    "POSTGRES_DB=aipp"
    "AIPP_LLM_KEY="
    "ANTHROPIC_API_KEY="
    "OPENAI_API_KEY="
    "GEMINI_API_KEY="
    "LLM_PROVIDER=anthropic"
    "LLM_MODEL=claude-sonnet-4-6"
    "AIPP_DEFAULT_ADMIN_EMAIL=admin@aipp.local"
    "AIPP_DEFAULT_ADMIN_PASSWORD=aipp-change-me"
    "N8N_BASE_URL="
    "N8N_API_KEY="
    "OIDC_PROVIDER=off"
    "OIDC_CLIENT_ID="
    "OIDC_CLIENT_SECRET="
    "OIDC_DISCOVERY_URL="
    "OIDC_TENANT_ID=common"
    "AIPP_PUBLIC_URL=http://localhost:3300"
    "AIPP_BACKEND_PUBLIC_URL=http://localhost:8001"
    "RESEND_API_KEY="
    "EMAIL_FROM=AIPP <noreply@aipp.local>"
)
for pair in "${REQUIRED_EMPTY_OK[@]}"; do
    key="${pair%%=*}"; def="${pair#*=}"
    if ! has_key "$key"; then
        set_key "$key" "$def"
        ok "Added missing key: $key"
    fi
done

# ---------- 5. generate JWT_SECRET / AIPP_FERNET_KEY if empty --------------
if ! has_key JWT_SECRET || [[ -z "$(val_of JWT_SECRET)" ]]; then
    new_jwt=$(python3 -c 'import secrets; print(secrets.token_hex(64))')
    set_key "JWT_SECRET" "$new_jwt"
    ok "Generated new JWT_SECRET  (existing sessions will need to re-login)"
else
    info "JWT_SECRET already set — kept as-is."
fi

if ! has_key AIPP_FERNET_KEY || [[ -z "$(val_of AIPP_FERNET_KEY)" ]]; then
    if ! python3 -c 'import cryptography' >/dev/null 2>&1; then
        fail "python3 -c 'from cryptography.fernet import Fernet' failed.
              Install with:  pip install cryptography"
    fi
    new_fernet=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
    set_key "AIPP_FERNET_KEY" "$new_fernet"
    ok "Generated new AIPP_FERNET_KEY  (any previously-saved Integration PATs must be re-added)"
else
    info "AIPP_FERNET_KEY already set — kept as-is."
fi

# ---------- 6. summary -----------------------------------------------------
echo
info "Final .env sanity check:"
awk -F= '
    /^[A-Z_]+=/ {
        v = $0; sub(/^[^=]+=/, "", v);
        printf "  %-30s %s\n", $1"=", (length(v)>0 ? "SET("length(v)")" : "empty");
    }
' "$ENV_FILE"

echo
ok "Done. Backup: $ENV_FILE.bak-$STAMP"
echo   "Next:"
echo   "  1. Verify AIPP_LLM_KEY is populated (or a vendor-specific key is set)."
echo   "  2. docker compose down"
echo   "  3. docker compose build --no-cache backend frontend"
echo   "  4. docker compose up -d && docker compose ps"
