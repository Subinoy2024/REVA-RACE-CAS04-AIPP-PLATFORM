# AIPP Runbook

Operational reference for running AIPP in dev, staging, or production.

---

## 1. First-time boot

```bash
git clone <this repo> aipp && cd aipp
cp .env.example .env               # Docker Compose reads this
```

Fill in **at minimum**:

| Variable | Why |
|---|---|
| `AIPP_LLM_KEY` **or** `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | Any of these unlocks the multi-agent workflow. |
| `JWT_SECRET` | 64+ chars entropy. `python -c "import secrets;print(secrets.token_hex(64))"` |
| `AIPP_FERNET_KEY` | Encrypts Integration PATs. `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `AIPP_DEFAULT_ADMIN_EMAIL` | Seeded on first boot. |
| `AIPP_DEFAULT_ADMIN_PASSWORD` | 12+ chars. Rotate via `.env` + backend restart. |
| `PROXY_API_KEY` | Shared bearer used by n8n workflows to call `/api/proxy/*`. `openssl rand -hex 32` |
| `SLACK_SIGNING_SECRET` | Required for HITL button clicks. Copy from Slack app → Basic Information. |

Then:

```bash
docker compose up -d --build
# UI:      http://localhost:3300
# API:     http://localhost:8001/api/
# Postgres: pgvector/pgvector:pg15 on 5432
```

---

## 2. Common operations

### Restart backend
```bash
docker compose restart backend
```

### Rotate default admin password
1. Edit `AIPP_DEFAULT_ADMIN_PASSWORD` in `.env`.
2. `docker compose restart backend` — seed script re-hashes on boot.

### Enable cloud identity (OIDC)
1. Register an app in Keycloak / Google Cloud / Azure Entra ID.
2. Redirect URI: `${AIPP_BACKEND_PUBLIC_URL}/api/auth/oidc/callback`.
3. Set `OIDC_PROVIDER=google|azure|keycloak`, `OIDC_CLIENT_ID`,
   `OIDC_CLIENT_SECRET`.
4. Restart backend, log in as admin, `POST /api/auth/oidc/enable` —
   this disables the seeded local admin.

### Rotate the Fernet encryption key
Rotating `AIPP_FERNET_KEY` invalidates all stored Integration PATs.
Procedure:
1. Warn users on the Integrations tab.
2. `DELETE FROM deployment_targets;` (audits are preserved in
   `deployments`; no PATs live there).
3. Rotate `AIPP_FERNET_KEY` in `.env`, `docker compose restart backend`.
4. Ask users to re-onboard each target.

### Backup Postgres
```bash
docker compose exec postgres pg_dump -U aipp aipp > aipp-$(date +%F).sql
```

Restore:
```bash
cat aipp-YYYY-MM-DD.sql | docker compose exec -T postgres psql -U aipp -d aipp
```

### Enable pgvector after upgrade
`pgvector/pgvector:pg15` bundles the extension but Alembic must enable
it:
```bash
docker compose exec backend alembic upgrade head
docker compose exec postgres psql -U aipp -d aipp -c "\dx"
# vector should appear in the extension list
```

---

## 3. Health checks

| URL | Expect |
|---|---|
| `http://localhost:8001/api/health` | `{"status":"ok"}` |
| `http://localhost:8001/api/` | version + configured MCP adapters |
| `http://localhost:8001/api/mcp/tools` | all 11 adapters listed |
| `http://localhost:8001/api/slack/health` | `{"ok":true,"signing_secret_configured":true}` |
| `http://localhost:8001/api/proxy/health` | AIPP proxy adapter status matrix |
| `http://localhost:8001/api/webhooks/health` | Grafana + Azure Monitor bridge alive |
| `http://localhost:3300/` | Gradio login page |

---

## 4. n8n workflow operations

All commands run from `n8n/` on the AIPP host. Reads `../.env` for
`N8N_BASE_URL` + `N8N_API_KEY` + `PROXY_API_KEY`.

### Regenerate + deploy every workflow
```bash
cd n8n
python3 build_workflows.py
bash scripts/deploy.sh --activate-all      # push + activate all 17
```

### Smoke-test all workflows
```bash
bash scripts/smoke_test_all.sh             # full run
bash scripts/smoke_test_all.sh --local-only    # skip Azure flows
bash scripts/smoke_test_all.sh --skip-deploy   # already deployed
```

Prints a colour-coded pass/fail matrix + `/api/proxy/health` snapshot.

### Reset demo state
```bash
bash scripts/demo_reset.sh                 # wipes old executions,
                                           # fires fresh HITL webhooks,
                                           # waits 8s to park
bash scripts/demo_reset.sh --keep          # skip cleanup
```

### Remove duplicate / ghost workflows in n8n
```bash
python3 scripts/dedupe_workflows.py --dry-run   # preview
python3 scripts/dedupe_workflows.py             # keep highest ID per name
```

### Push variables (only for n8n Enterprise / self-hosted with Variables API)
```bash
bash scripts/push_variables.sh --dry-run
bash scripts/push_variables.sh
```

Community Edition does NOT support Variables API — workflows are
generated with inlined config instead.

---

## 5. Slack HITL bridge

- Slack app manifest lives in `n8n/README.md`.
- **Interactivity Request URL**: `https://<aipp-public-url>/api/slack/interactions`
- Test the bridge end-to-end:
  ```bash
  bash scripts/hitl_demo.sh                  # fires a synthetic webhook,
                                             # parks at Wait, posts to Slack
  ```
- Approvals audit tab in the UI shows every click; API mirror:
  ```bash
  curl -s http://localhost:8001/api/slack/approvals | jq
  ```

---

## 6. Auto-Deploy safety net

- All writes go to the **onboarded deployment repository**, never the
  analysed source repo.
- `mode="pr"` (default) opens a PR the user must review and merge.
- `mode="commit"` refuses to auto-create branches; the target branch
  must already exist on the deployment repo.
- Confirm-checkbox is mandatory in the UI before the deploy button
  becomes clickable.
- Every attempt (success or failure) is persisted to the `deployments`
  table with the YAML SHA-256, commit SHA, PR URL, and any error.

To disable auto-deploy platform-wide, drop the router include for
`integrations.router` in `backend/server.py` and rebuild.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `500 Fernet key not set` in Integrations | `AIPP_FERNET_KEY` missing — set it and restart. |
| `Refusing to commit — YAML contains secrets` | The generated YAML failed the secret scanner. Regenerate. |
| `Branch 'main' does not exist` | Direct-commit mode; branch must already exist on the deployment repo. |
| PR creation returns 409 | A PR from the same head branch already exists — the API returns a URL to the PR list; open it manually. |
| OIDC callback → 400 "OIDC user has no verified email" | Provider returned `email_verified=false`. Verify the account first. |
| `/api/slack/interactions` → 401 "bad signature" | `SLACK_SIGNING_SECRET` in AIPP `.env` doesn't match the Slack app value. Copy again from Slack → Basic Information. |
| `/api/slack/interactions` → 401 "stale request" | Request older than 5 min — Slack retries within its own retry policy; check clock skew on the AIPP host. |
| n8n workflow parked at Wait but Slack click does nothing | Interactivity URL not set in Slack app manifest, or Slack bot not invited to the channel. |
| `smoke_test_all.sh` shows workflow-14 chaos returns HTTP 500 | Form Trigger expects `multipart/form-data` — patched in latest script; pull the newest `smoke_test_all.sh`. |
| `pipeline-doctor/similar` returns `hits: 0` on a fresh DB | Expected — `rca_embeddings` is empty until you analyse a few RCAs. |

---

## 8. Tests

```bash
python -m pytest backend/tests/ -q -n 2 --dist loadscope
```

Full suite runs in ≈15 s. Contract-level tests (no external services)
live in `test_iteration_*.py` and `test_n8n_workflows.py`;
live-backend tests (require Postgres + running uvicorn) are in
`backend_test.py` and `test_deployment_and_generators.py`.

Slack + HITL bridge:
```bash
python -m pytest backend/tests/test_slack_interactions.py -q
python -m pytest backend/tests/test_hitl_and_webhooks.py -q
python -m pytest backend/tests/test_rca_embedding.py -q
```
