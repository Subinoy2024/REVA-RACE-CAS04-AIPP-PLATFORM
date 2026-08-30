# AIPP — Manual Deployment Guide

_Last updated: February 2026 · Iteration-34 (PipelineDoctor RAG + Slack Block Kit HITL)_

Step-by-step instructions to bring **AIPP** up from a fresh clone to a
signed-in, YAML-generating, auto-deploying instance with **17 n8n
workflows + Slack HITL approvals + pgvector RAG memory**. Works on any
host that runs Docker Compose (Ubuntu, Debian, macOS, WSL2, or a VM on
Azure/AWS/GCP).

---

## 0. Prerequisites

| Tool | Minimum version | Why |
|---|---|---|
| Docker | 24.x | Container runtime |
| Docker Compose | v2 (built-in `docker compose`) | 3-service stack |
| Git | any recent | Clone + push |
| Python | 3.11 (only if running tests / build_workflows outside Docker) | pytest + `n8n/build_workflows.py` |

Optional (but recommended):
- `openssl` — to generate JWT / Fernet / proxy secrets
- A **GitHub PAT** with `repo` + `workflow` scopes (needed for
  repository analysis and Auto-Deploy)
- An **LLM key**: `AIPP_LLM_KEY` **or** any one of
  `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY`
- A **Slack app** with Interactivity enabled (see § 4 for setup)
- An external **n8n instance** (Community Edition is fully supported)

---

## 1. Clone the repository

```bash
git clone https://github.com/<your-org>/aipp.git
cd aipp
```

---

## 2. One-click bootstrap (recommended)

The repo ships a single script that generates all secrets, writes both
`.env` files, and boots the stack:

```bash
# Linux / macOS / WSL
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

```powershell
# Windows PowerShell
.\scripts\bootstrap.ps1
```

The script:
1. Verifies `docker`, `docker compose` v2, and `python3` are installed.
2. Generates a fresh `JWT_SECRET` and `AIPP_FERNET_KEY` (or reuses the
   ones already in `.env`).
3. Prompts once for your LLM key (universal AIPP_LLM_KEY or Anthropic / OpenAI /
   Gemini) — or reads it from the `LLM_KEY` env var for CI usage.
4. Writes `.env` and `.env` with mode `600`.
5. Runs `docker compose up -d --build` and waits for
   `/api/health` to return `200`.
6. Prints the UI URL + login credentials.

Non-interactive example (CI):
```bash
LLM_KEY="sk-emergent-abc" ./scripts/bootstrap.sh
```

If you'd rather do it by hand, see the next section.

## 2b. Manual environment setup

```bash
cp .env.example .env
cp .env.example .env   # backend also reads its own copy
```

Open `.env` and fill in **at minimum**:

```env
# --- Database (compose builds the connection URL from these three) ---
POSTGRES_USER=aipp
POSTGRES_PASSWORD=aipp_local
POSTGRES_DB=aipp
# Do NOT set DATABASE_URL / POSTGRES_URL yourself — Docker Compose
# derives them from POSTGRES_* above so backend + Postgres always agree.

# --- LLM (any one of these is enough) ---
AIPP_LLM_KEY=your-universal-llm-api-key
# ANTHROPIC_API_KEY=sk-ant-....
# OPENAI_API_KEY=sk-....
# GEMINI_API_KEY=....

# --- Auth ---
JWT_SECRET=<paste 64+ random chars — see command below>
AIPP_DEFAULT_ADMIN_EMAIL=admin@yourcompany.com
AIPP_DEFAULT_ADMIN_PASSWORD=<pick a strong 12+ char password>

# --- Auto-Deploy encryption (Integrations tab) ---
AIPP_FERNET_KEY=<paste output of the Fernet command below>
```

Generate the two secrets:

```bash
# JWT secret (64+ random chars)
python3 -c "import secrets; print(secrets.token_hex(64))"

# Fernet key (32-byte base64) — used to encrypt user PATs at rest
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> 🔒 **Do NOT commit `.env` or `.env`** — `.gitignore` already
> excludes them.

Optional extras (leave blank to skip):

```env
# --- n8n integration (AIPP works with your existing n8n instance) ---
N8N_BASE_URL=https://n8n.yourcompany.com
N8N_API_KEY=n8n-....

# --- Secret-Vault Proxy (n8n calls AIPP; AIPP holds the real infra secrets) ---
PROXY_API_KEY=<openssl rand -hex 32 — shared bearer used by every workflow>

# --- Slack HITL bridge (required for Block Kit button clicks) ---
SLACK_SIGNING_SECRET=<from Slack app → Basic Information>

# --- Real infra credentials that n8n workflows fan out via /api/proxy/* ---
K8S_API_URL=https://<cluster-api>
K8S_TOKEN=<service-account-token>
K8S_CA_VERIFY=false          # true in prod
GITHUB_PAT=ghp_....
GH_ORG=your-org
GH_REPO_ALLOWLIST=org/repo1,org/repo2
GRAFANA_URL=https://grafana.yourcompany.com
GRAFANA_API_KEY=....
PROXMOX_URL=https://proxmox.local:8006
PROXMOX_NODE=pve1
PROXMOX_TOKEN='user@pam!token=<uuid>'
ADO_ORG=<slug>
ADO_PROJECT=<slug>
ADO_PAT=<pat>

# --- OIDC (Keycloak / Google Workspace / Azure Entra ID) ---
OIDC_PROVIDER=keycloak       # or "google" or "azure"
OIDC_CLIENT_ID=....
OIDC_CLIENT_SECRET=....
OIDC_DISCOVERY_URL=https://keycloak.yourcompany.com/realms/aipp/.well-known/openid-configuration
AIPP_BACKEND_PUBLIC_URL=http://localhost:8001

# --- Password-reset email (Resend). Leave blank in dev — links log to stdout. ---
RESEND_API_KEY=re_....
EMAIL_FROM=AIPP <noreply@yourcompany.com>
```

---

## 3. Start the stack

```bash
docker compose up -d --build
```

First build takes ~2–3 min. Watch logs:

```bash
docker compose logs -f backend
```

You should see:
```
INFO  Uvicorn running on http://0.0.0.0:8001
INFO  Alembic: applied migration 0c995b5f4ca3
INFO  aipp.seed: default admin admin@yourcompany.com created
```

---

## 4. Verify health

```bash
curl -s http://localhost:8001/api/health
# → {"status":"ok"}

curl -s http://localhost:8001/api/mcp/tools | jq '.total'
# → 11
```

Open the UI: **http://localhost:3300**

You should see the futuristic **AIPP Control Tower** login screen (dark
glass background, neon-purple gradient).

Sign in with:
- **Email**: `AIPP_DEFAULT_ADMIN_EMAIL` you set in `.env`
- **Password**: `AIPP_DEFAULT_ADMIN_PASSWORD` you set in `.env`

---

## 5. First-run acceptance checklist

Walk through this once — it's your smoke test.

- [ ] **Login** → dashboard renders with **13 tabs**
- [ ] **Pipeline Generator** → paste a public GitHub repo URL + your PAT
      + pick `github_actions` + `aws`. Click **Generate**. Watch agent
      orbs light up + YAML render in the preview.
- [ ] **Integrations tab** → **Onboard a new deployment target**:
    - Nickname: `My Deploy Repo`
    - Platform: `GitHub Actions` (or Azure DevOps / GitLab CI)
    - Deployment repo URL: `https://github.com/<you>/<a-repo-you-own>`
    - Default branch: `main`
    - PAT: paste a **write-scoped** PAT (`repo` + `workflow`)
    - Click **Add integration** → success banner
- [ ] Back in **Pipeline Generator** → scroll down → change delivery
      radio to **Auto-push via AIPP** → **↻ Load my integrations** →
      pick the target → check the confirm box → **🚀 Confirm &
      auto-deploy**
- [ ] Open the returned PR URL in a new tab → you should see a fresh
      branch `aipp/pipeline-XXXXXXXX` with the generated YAML at
      `.github/workflows/aipp-pipeline.yml`
- [ ] **Integrations → Deployment history** → row shows `success` ✅
      with a link back to the PR

If every box is ticked, AIPP is fully operational.

---

## 5b. n8n + Slack HITL bring-up

Once AIPP itself is running, wire in the 17 n8n workflows and the Slack
approvals bridge.

### 5b.1 Set up your Slack app (once, ~5 min)

1. https://api.slack.com/apps → **Create New App** → From scratch → name
   it *AIPP*.
2. **OAuth & Permissions** → add scopes:
   * `chat:write` — post messages
   * `channels:read` — resolve channel names
   * `chat:write.customize` — post as AIPP identity
3. **Interactivity & Shortcuts** → toggle **on** → Request URL:
   `https://<aipp-public-url>/api/slack/interactions`
4. Install to workspace → copy the **Bot User OAuth Token** (`xoxb-…`)
   → set it in n8n as credential `slack-aipp`.
5. **Basic Information** → copy **Signing Secret** → set as
   `SLACK_SIGNING_SECRET` in AIPP `.env` and `docker compose restart backend`.
6. Create these channels and invite the AIPP bot:
   `#platform-approvals` `#platform-drift` `#platform-provisioning`
   `#platform-status` `#platform-k8s` `#platform-troubleshoot`
   `#platform-alerts` `#finops` `#security-access-review`
   `#incidents` `#incident-comms` `#sre-runbooks` `#sre-slo`
   `#sre-dr` `#sre-chaos` `#sre-logs`

### 5b.2 Build + deploy the 17 workflows

```bash
cd n8n
python3 build_workflows.py                 # regenerates all 17 JSONs
bash scripts/deploy.sh --activate-all      # pushes + activates
```

Reads `../.env` for `N8N_BASE_URL`, `N8N_API_KEY`, `PROXY_API_KEY`, and
all infra credentials.

### 5b.3 Smoke-test the workflows

```bash
bash scripts/smoke_test_all.sh --local-only
```

Prints a colour-coded pass/fail matrix. HITL flows will show as
`running` — that's correct; they're parked waiting for Slack input.

### 5b.4 Verify HITL end-to-end

```bash
bash scripts/hitl_demo.sh
```

Watch `#platform-approvals` in Slack → click ✅ Approve on the card →
Slack card reseals to "✅ Approved by @you". Then check the Approvals
tab in the AIPP UI — the row appears within 5 s.

---

## 6. Common operations

### Restart backend after a `.env` change
```bash
docker compose restart backend
```

### Rotate the seeded admin password
1. Edit `AIPP_DEFAULT_ADMIN_PASSWORD` in `.env`.
2. `docker compose restart backend` — the seed script re-hashes on boot.

### Enable OIDC (Google / Azure AD)
1. Register the app in the provider console.
2. Redirect URI: `${AIPP_BACKEND_PUBLIC_URL}/api/auth/oidc/callback`
3. Fill `OIDC_*` env vars.
4. `docker compose restart backend` → the OIDC button appears on the
   login page.

### Backup Postgres
```bash
docker compose exec postgres pg_dump -U aipp aipp > aipp-$(date +%F).sql
```

### Rotate the Fernet encryption key
Rotating `AIPP_FERNET_KEY` invalidates every stored PAT in
`deployment_targets`. Procedure:
1. Notify users via the Integrations tab.
2. `docker compose exec postgres psql -U aipp -d aipp -c "DELETE FROM deployment_targets;"`
   (audit history in `deployments` is preserved — no PATs there.)
3. Update `AIPP_FERNET_KEY` in `.env` + `.env`.
4. `docker compose restart backend`.
5. Users re-onboard each target.

### Update the app
```bash
git pull
docker compose up -d --build
```
Alembic auto-runs pending migrations on start.

### Uninstall
```bash
docker compose down -v   # -v also drops the Postgres volume
```

### Password mismatch after editing `.env`

Postgres bakes the initial `POSTGRES_PASSWORD` into its data volume on the
**first boot only**. If you change it in `.env` later, the backend
starts using the new password but Postgres still holds the old one — you
see `password authentication failed for user "aipp"` in the backend logs.

Two ways out:

* **Fast + destructive** (safe if you haven't onboarded real data yet):
  ```bash
  docker compose down -v
  docker compose up -d --build
  ```

* **Non-destructive** — rotate the password inside Postgres to match `.env`:
  ```bash
  NEW_PW=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
  docker compose exec -T postgres psql -U aipp -d postgres <<SQL
  ALTER USER aipp WITH PASSWORD '${NEW_PW}';
  SQL
  docker compose restart backend
  ```

---

## 7. Deploying AIPP to a cloud host

The stack is a plain Docker Compose project — deploy it anywhere.

### Azure
1. Create a Linux VM (B2s or larger).
2. Install Docker: `curl -fsSL https://get.docker.com | sh`
3. Clone repo, populate `.env`, `docker compose up -d --build`.
4. Point an Azure DNS record + open ports 3300 (UI) and 8001 (API) in
   the NSG. Front with Nginx / Azure Front Door for TLS.

### AWS
1. Launch an EC2 t3.small or larger.
2. Same steps as Azure. Front with an ALB + ACM cert for HTTPS.

### GCP
1. Compute Engine `e2-medium`. Same recipe.
2. Front with Cloud Load Balancer + managed TLS.

### Kubernetes (advanced)
AIPP ships with plain Compose. To move to K8s:
1. `docker compose convert -f docker-compose.yml > k8s.yaml`
2. Tune resource limits + add a `PersistentVolumeClaim` for Postgres.
3. Add a `ConfigMap` for env + `Secret` for `JWT_SECRET`, `AIPP_FERNET_KEY`.

---

## 8. Troubleshooting

| Symptom                                            | Fix |
|----------------------------------------------------|-----|
| `password authentication failed for user "aipp"` in backend logs + `relation "users" does not exist` | You changed `POSTGRES_PASSWORD` in `.env` **after** the Postgres volume was created. Postgres kept the old password in its data directory. Fix: `docker compose down -v && docker compose up -d --build` (wipes DB, safe if no real data yet). See §6 "Password mismatch" below for a non-destructive path. |
| `backend` container restarting                     | `docker compose logs backend` — usually a missing env var. |
| UI hangs at "Loading…"                             | Browser can't reach the backend on `:8001`. Check firewall + `AIPP_BACKEND_PUBLIC_URL`. |
| Login fails with valid credentials                 | Backend can't reach Postgres. Verify `DATABASE_URL` + `docker compose ps postgres`. |
| `500 Fernet key not set` on Integrations           | `AIPP_FERNET_KEY` empty — generate one and restart. |
| Auto-deploy PR returns `Refusing to deploy — YAML contains suspected secrets` | The generated YAML failed the secret scanner. Regenerate or scrub inline creds. |
| Auto-deploy fails with `Branch 'main' does not exist` | Direct-commit mode was chosen but the branch is missing on the deployment repo. Switch to PR mode or pre-create the branch. |
| OIDC returns 400 "no verified email"               | Google/Azure account isn't verified. Verify + retry. |

---

## 9. Pushing the codebase to GitHub

The safest way is the built-in **Save to GitHub** action in the chat
input — it handles auth + CI-friendly commits for you.

If you prefer the CLI:

```bash
cd /app
git init -b main               # if not already a repo
git add .
git commit -m "AIPP v0.25 — Auto-Deploy shipped"
git remote add origin https://github.com/<you>/aipp.git
git push -u origin main
```

`.gitignore` protects your `.env` files. `.env.example` **is** committed
by design so new contributors have a template.

---

## 10. Test suite

Fully offline (no external services needed):

```bash
docker compose exec backend python -m pytest backend/tests/ \
  --ignore=backend/tests/backend_test.py \
  --ignore=backend/tests/test_deployment_and_generators.py -q
# → 477 passed, 2 skipped
```

Full suite (needs the live stack up):

```bash
docker compose exec backend python -m pytest backend/tests/ -q
# → 489 passed, 2 skipped
```

---

**That's it.** For a deeper operational reference (backups, key
rotation, cloud sizing), see [`docs/RUNBOOK.md`](RUNBOOK.md).
For the current feature inventory, see [`docs/STATUS.md`](STATUS.md).
