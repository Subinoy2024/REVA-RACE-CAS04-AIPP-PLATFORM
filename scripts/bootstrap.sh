#!/usr/bin/env bash
# =============================================================================
# AIPP · one-click bootstrap
# -----------------------------------------------------------------------------
# Idempotent: safe to run again to top up missing secrets / restart the stack.
#
#   ./scripts/bootstrap.sh                   # interactive (prompts for LLM key)
#   LLM_KEY=sk-emergent-... ./scripts/bootstrap.sh   # non-interactive
#   ./scripts/bootstrap.sh --no-up           # only write .env files, skip boot
#
# What it does:
#   1. Verifies docker + docker compose + python3 exist
#   2. Generates JWT_SECRET + AIPP_FERNET_KEY (only if not already set)
#   3. Writes .env and .env (copies) with sensible defaults
#   4. Prompts once for an LLM key (skipped if $LLM_KEY is exported)
#   5. Runs `docker compose up -d --build`
#   6. Waits for /api/health and prints login credentials
# =============================================================================
set -euo pipefail

# ---------- pretty output ----------
c_red='\033[0;31m'; c_grn='\033[0;32m'; c_ylw='\033[1;33m'; c_blu='\033[0;34m'; c_off='\033[0m'
say()  { printf "${c_blu}▶${c_off} %s\n" "$*"; }
ok()   { printf "${c_grn}✔${c_off} %s\n" "$*"; }
warn() { printf "${c_ylw}!${c_off} %s\n" "$*"; }
die()  { printf "${c_red}✘${c_off} %s\n" "$*" >&2; exit 1; }

ROOT="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )/.." &>/dev/null && pwd )"
cd "$ROOT"

# ---------- arg parsing ----------
DO_UP=1
for arg in "$@"; do
  case "$arg" in
    --no-up) DO_UP=0 ;;
    -h|--help)
      grep -E '^#( |$)' "$0" | sed 's/^# \?//' ; exit 0 ;;
  esac
done

echo
say "AIPP bootstrap — repo root: $ROOT"
echo

# ---------- 1. prerequisites ----------
say "Checking prerequisites"
command -v docker >/dev/null 2>&1 || die "docker not found — install Docker Desktop or Docker Engine"
docker compose version >/dev/null 2>&1 || die "docker compose v2 not found — upgrade Docker"
command -v python3 >/dev/null 2>&1 || die "python3 not found (needed only to generate secrets)"
ok "docker, docker compose, python3 present"

# ---------- 2. secrets ----------
say "Generating secrets (only if missing)"

_gen_jwt()    { python3 -c 'import secrets; print(secrets.token_hex(64))'; }
_gen_fernet() {
  python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || {
    # cryptography not installed on host — fall back to docker one-liner
    docker run --rm python:3.11-slim sh -c \
      "pip install --quiet cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
  }
}

# If .env exists already, keep the existing keys — never rotate silently.
_read_existing() {
  local key="$1"; local file="$2"
  [[ -f "$file" ]] && grep -E "^${key}=" "$file" | head -n1 | cut -d= -f2- || true
}

JWT_SECRET_VAL="$(_read_existing JWT_SECRET .env)"
FERNET_VAL="$(_read_existing AIPP_FERNET_KEY .env)"

[[ -z "$JWT_SECRET_VAL" || "$JWT_SECRET_VAL" == *change-me* ]] && JWT_SECRET_VAL="$(_gen_jwt)"      && ok "generated new JWT_SECRET"
[[ -z "$FERNET_VAL"     ]]                                    && FERNET_VAL="$(_gen_fernet)"       && ok "generated new AIPP_FERNET_KEY"

# ---------- 3. LLM key ----------
say "LLM key"
LLM_KEY="${LLM_KEY:-}"
if [[ -z "$LLM_KEY" ]]; then
  # try to preserve whatever the user already put in .env
  for k in EMERGENT_LLM_KEY ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY; do
    v="$(_read_existing "$k" .env)"
    if [[ -n "$v" ]]; then LLM_KEY="$v"; LLM_KEY_VAR="$k"; break; fi
  done
fi
if [[ -z "$LLM_KEY" ]]; then
  warn "No LLM key found in .env or \$LLM_KEY"
  echo   "  Paste an Emergent / Anthropic / OpenAI / Gemini key now, or press Enter to leave blank."
  echo   "  You can always add it later by editing .env and running: docker compose restart backend"
  read -r -p "  LLM key: " LLM_KEY || true
fi

# Auto-detect vendor from the key prefix so we don't dump an OpenAI key
# into EMERGENT_LLM_KEY (or similar) by accident.
if [[ -n "$LLM_KEY" ]]; then
  case "$LLM_KEY" in
    sk-emergent-*)            LLM_KEY_VAR="EMERGENT_LLM_KEY" ;;
    sk-ant-*)                 LLM_KEY_VAR="ANTHROPIC_API_KEY" ;;
    sk-proj-*|sk-*)           LLM_KEY_VAR="OPENAI_API_KEY" ;;
    AIza*|ya29.*)             LLM_KEY_VAR="GEMINI_API_KEY" ;;
    *)                        : ;;   # leave whatever was pre-set
  esac
fi
LLM_KEY_VAR="${LLM_KEY_VAR:-EMERGENT_LLM_KEY}"
[[ -n "$LLM_KEY" ]] && ok "using ${LLM_KEY_VAR}" || warn "no LLM key — pipeline generation will fail until one is added"

# ---------- 4. admin credentials ----------
ADMIN_EMAIL_VAL="$(_read_existing AIPP_DEFAULT_ADMIN_EMAIL .env)"
ADMIN_PW_VAL="$(_read_existing AIPP_DEFAULT_ADMIN_PASSWORD .env)"
ADMIN_EMAIL_VAL="${ADMIN_EMAIL_VAL:-admin@aipp.local}"
ADMIN_PW_VAL="${ADMIN_PW_VAL:-aipp-change-me}"

# ---------- 5. write env files ----------
say "Writing .env (single source of truth at repo root)"
cat > .env <<EOF
# ---------- Database ----------
# Docker Compose builds the connection URL from these three values.
# Do NOT add DATABASE_URL / POSTGRES_URL here — compose derives them.
POSTGRES_USER=aipp
POSTGRES_PASSWORD=aipp_local
POSTGRES_DB=aipp

# ---------- LLM (pick ONE — non-selected lines stay blank) ----------
EMERGENT_LLM_KEY=$([[ "$LLM_KEY_VAR" == "EMERGENT_LLM_KEY" ]] && echo "$LLM_KEY")
ANTHROPIC_API_KEY=$([[ "$LLM_KEY_VAR" == "ANTHROPIC_API_KEY" ]] && echo "$LLM_KEY")
OPENAI_API_KEY=$([[ "$LLM_KEY_VAR" == "OPENAI_API_KEY" ]] && echo "$LLM_KEY")
GEMINI_API_KEY=$([[ "$LLM_KEY_VAR" == "GEMINI_API_KEY" ]] && echo "$LLM_KEY")

# ---------- Auth ----------
JWT_SECRET=${JWT_SECRET_VAL}
AIPP_DEFAULT_ADMIN_EMAIL=${ADMIN_EMAIL_VAL}
AIPP_DEFAULT_ADMIN_PASSWORD=${ADMIN_PW_VAL}

# ---------- Auto-Deploy encryption (Integrations tab) ----------
AIPP_FERNET_KEY=${FERNET_VAL}

# ---------- Optional integrations ----------
N8N_BASE_URL=
N8N_API_KEY=
OIDC_PROVIDER=off
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=
OIDC_DISCOVERY_URL=
AIPP_BACKEND_PUBLIC_URL=http://localhost:8001
AIPP_PUBLIC_URL=http://localhost:3300
RESEND_API_KEY=
EMAIL_FROM=AIPP <noreply@aipp.local>

# ---------- Runtime ----------
CORS_ORIGINS=*
AIPP_MCP_GUARD=block
AIPP_INTERNAL_BACKEND_URL=http://127.0.0.1:8001
LOG_LEVEL=INFO
MAX_LOG_UPLOAD_BYTES=5000000
EOF
chmod 600 .env
ok ".env written (mode 600) — single source of truth at repo root"

# Legacy: earlier versions of AIPP wrote a duplicate `backend/.env`.
# Remove it if present so it can never drift out of sync with the real
# `.env` at the repo root.
if [[ -f backend/.env ]]; then
    rm -f backend/.env
    ok "removed legacy backend/.env — only .env at repo root is used now"
fi

if [[ "$DO_UP" -eq 0 ]]; then
  echo
  ok "Env files ready. Skipped 'docker compose up' (--no-up)."
  echo "Next:  docker compose up -d --build"
  exit 0
fi

# ---------- 6. boot ----------
say "Building + starting the Docker Compose stack (this can take 2–3 min the first time)"
docker compose up -d --build

# ---------- 7. wait for health ----------
say "Waiting for backend health"
tries=60
until curl -sf http://localhost:8001/api/health >/dev/null 2>&1; do
  tries=$((tries-1))
  if [[ $tries -le 0 ]]; then
    warn "Backend did not report healthy in 60s — check: docker compose logs backend"
    break
  fi
  sleep 1
done
[[ $tries -gt 0 ]] && ok "backend healthy at http://localhost:8001/api/health"

# ---------- 8. summary ----------
echo
printf "${c_grn}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${c_off}\n"
printf "${c_grn} AIPP is up 🚀${c_off}\n"
printf "${c_grn}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${c_off}\n"
echo   "  UI    : http://localhost:3300"
echo   "  API   : http://localhost:8001/api/"
echo   "  Login : ${ADMIN_EMAIL_VAL}  /  ${ADMIN_PW_VAL}"
echo
echo   "  Logs  : docker compose logs -f backend"
echo   "  Stop  : docker compose down"
echo   "  Reset : docker compose down -v   (also drops the Postgres volume)"
echo
[[ -z "$LLM_KEY" ]] && warn "LLM key not set — add one to .env then: docker compose restart backend"
echo
