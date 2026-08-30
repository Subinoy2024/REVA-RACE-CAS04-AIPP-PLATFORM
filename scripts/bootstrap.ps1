# =============================================================================
# AIPP · one-click bootstrap (Windows PowerShell 5+ / 7+)
# -----------------------------------------------------------------------------
# Usage:
#   .\scripts\bootstrap.ps1                        # interactive
#   .\scripts\bootstrap.ps1 -LlmKey "sk-emergent..."
#   .\scripts\bootstrap.ps1 -NoUp                  # only write .env files
# =============================================================================
[CmdletBinding()]
param(
  [string]$LlmKey = $env:LLM_KEY,
  [string]$LlmKeyVar = "EMERGENT_LLM_KEY",
  [switch]$NoUp
)

$ErrorActionPreference = "Stop"
function Say  ($m) { Write-Host "▶ $m" -ForegroundColor Blue }
function Ok   ($m) { Write-Host "✔ $m" -ForegroundColor Green }
function Warn ($m) { Write-Host "! $m" -ForegroundColor Yellow }
function Die  ($m) { Write-Host "✘ $m" -ForegroundColor Red; exit 1 }

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Say "AIPP bootstrap — repo root: $Root"

# 1. prerequisites
Say "Checking prerequisites"
if (-not (Get-Command docker -EA SilentlyContinue))  { Die "docker not found" }
if (-not (Get-Command python -EA SilentlyContinue) -and -not (Get-Command python3 -EA SilentlyContinue)) { Die "python not found" }
$py = (Get-Command python -EA SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python3 -EA SilentlyContinue).Source }
docker compose version *> $null; if ($LASTEXITCODE -ne 0) { Die "docker compose v2 not found" }
Ok "docker + python present"

# 2. secrets — reuse existing if backend/.env already has them
function ReadEnv([string]$key, [string]$file) {
  if (Test-Path $file) {
    ($v = (Select-String -Path $file -Pattern "^$key=" -SimpleMatch:$false -EA SilentlyContinue).Line) | Out-Null
    if ($v) { return ($v -split '=', 2)[1] }
  }
  return $null
}

$JwtSecret = ReadEnv "JWT_SECRET" "backend/.env"
if (-not $JwtSecret -or $JwtSecret -like "*change-me*") {
  $JwtSecret = & $py -c "import secrets; print(secrets.token_hex(64))"
  Ok "generated new JWT_SECRET"
}

$Fernet = ReadEnv "AIPP_FERNET_KEY" "backend/.env"
if (-not $Fernet) {
  $Fernet = & $py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>$null
  if (-not $Fernet) {
    Warn "cryptography not installed on host — using docker one-liner"
    $Fernet = docker run --rm python:3.11-slim sh -c "pip install --quiet cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
  }
  Ok "generated new AIPP_FERNET_KEY"
}

# 3. LLM key
if (-not $LlmKey) {
  foreach ($k in @("EMERGENT_LLM_KEY","ANTHROPIC_API_KEY","OPENAI_API_KEY","GEMINI_API_KEY")) {
    $v = ReadEnv $k "backend/.env"
    if ($v) { $LlmKey = $v; $LlmKeyVar = $k; break }
  }
}
if (-not $LlmKey) {
  Warn "No LLM key found."
  $LlmKey = Read-Host "  Paste an Emergent / Anthropic / OpenAI / Gemini key (or press Enter to skip)"
}
# Auto-detect vendor from prefix
if ($LlmKey) {
  switch -Wildcard ($LlmKey) {
    'sk-emergent-*' { $LlmKeyVar = 'EMERGENT_LLM_KEY' }
    'sk-ant-*'      { $LlmKeyVar = 'ANTHROPIC_API_KEY' }
    'sk-proj-*'     { $LlmKeyVar = 'OPENAI_API_KEY' }
    'sk-*'          { $LlmKeyVar = 'OPENAI_API_KEY' }
    'AIza*'         { $LlmKeyVar = 'GEMINI_API_KEY' }
  }
}
if ($LlmKey) { Ok "using $LlmKeyVar" } else { Warn "no LLM key — pipeline generation will fail until one is added" }

# 4. admin creds
$AdminEmail = ReadEnv "AIPP_DEFAULT_ADMIN_EMAIL" "backend/.env"; if (-not $AdminEmail) { $AdminEmail = "admin@aipp.local" }
$AdminPw    = ReadEnv "AIPP_DEFAULT_ADMIN_PASSWORD" "backend/.env"; if (-not $AdminPw) { $AdminPw = "aipp-change-me" }

# 5. write env files
Say "Writing backend/.env"
if (-not (Test-Path "backend")) { New-Item -ItemType Directory -Path "backend" | Out-Null }
$envBody = @"
# Docker Compose builds the DB URL from these three values.
# Do NOT set DATABASE_URL / POSTGRES_URL here.
POSTGRES_USER=aipp
POSTGRES_PASSWORD=aipp_local
POSTGRES_DB=aipp

EMERGENT_LLM_KEY=$(if ($LlmKeyVar -eq "EMERGENT_LLM_KEY") { $LlmKey })
ANTHROPIC_API_KEY=$(if ($LlmKeyVar -eq "ANTHROPIC_API_KEY") { $LlmKey })
OPENAI_API_KEY=$(if ($LlmKeyVar -eq "OPENAI_API_KEY") { $LlmKey })
GEMINI_API_KEY=$(if ($LlmKeyVar -eq "GEMINI_API_KEY") { $LlmKey })

JWT_SECRET=$JwtSecret
AIPP_DEFAULT_ADMIN_EMAIL=$AdminEmail
AIPP_DEFAULT_ADMIN_PASSWORD=$AdminPw

AIPP_FERNET_KEY=$Fernet

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

CORS_ORIGINS=*
AIPP_MCP_GUARD=block
AIPP_INTERNAL_BACKEND_URL=http://127.0.0.1:8001
LOG_LEVEL=INFO
MAX_LOG_UPLOAD_BYTES=5000000
"@
Set-Content -Path "backend/.env" -Value $envBody -Encoding UTF8
Copy-Item "backend/.env" ".env" -Force
Ok "backend/.env and .env written"

if ($NoUp) { Ok "Env files ready. Skipped 'docker compose up' (-NoUp)."; exit 0 }

# 6. boot
Say "Building + starting the Docker Compose stack"
docker compose up -d --build

# 7. wait for health
Say "Waiting for backend health"
$tries = 60
while ($tries -gt 0) {
  try { Invoke-WebRequest "http://localhost:8001/api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch {}
  Start-Sleep -Seconds 1
  $tries--
}
if ($tries -le 0) { Warn "Backend did not report healthy in 60s — check: docker compose logs backend" }
else { Ok "backend healthy" }

# 8. summary
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host " AIPP is up 🚀" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "  UI    : http://localhost:3300"
Write-Host "  API   : http://localhost:8001/api/"
Write-Host "  Login : $AdminEmail  /  $AdminPw"
Write-Host ""
Write-Host "  Logs  : docker compose logs -f backend"
Write-Host "  Stop  : docker compose down"
Write-Host "  Reset : docker compose down -v"
if (-not $LlmKey) { Write-Host ""; Warn "LLM key not set — edit backend/.env then: docker compose restart backend" }
