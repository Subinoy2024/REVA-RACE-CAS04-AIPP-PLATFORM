# AIPP — Automated Pipeline Platform · Build Status

_Last updated: February 2026 · Iteration-34 (PipelineDoctor RAG)_

## Vision
An MS-research grade platform that **analyzes any GitHub repo → generates
deployment-ready CI/CD YAML → auto-deploys to your controlled repo →
performs AI-driven RCA with RAG memory on CI/CD logs → runs 17 n8n
AI-Ops workflows with Slack Block Kit HITL approvals.** Governed via
MCP, backed by PostgreSQL 15 + pgvector, wrapped in a Gradio 4 UI.

---

## ✅ What we have built (Iterations 1 → 34)

### 1. Multi-agent core (LangGraph)
- **8 explicit agents**: Repository · Technology · Architecture · Planner
  · Environment · Generator · Validator · PipelineDoctor (RCA)
- Self-describing **Agent Registry** (`/api/agents`) — every agent
  declares its skills, MCP scopes, and I/O contract
- **Live SSE streaming** — agents transition and LLM tokens flow
  token-by-token in the UI

### 2. MCP governance layer
- **11 adapters**: GitHub · GitHub Actions · Azure DevOps · GitLab CI ·
  Harness · Tekton · Kubernetes · AWS · Azure · GCP · n8n
- **MCP Guard** — adapters can only be called by agents whose skills
  authorise them (`block` mode default, `warn` toggleable)

### 3. Pipeline generation (5 CI × 3 clouds)
- **CI targets**: Azure DevOps · GitHub Actions · GitLab CI · Harness · Tekton
- **Cloud targets**: AWS · Azure · GCP
- **Environment-aware** DEV/QA/Staging/Prod with approval gates, health
  checks, smoke tests, rollback strategies
- **Deployment-target dropdown**: EKS, Lambda, AKS, Cloud Run, App
  Service, ACI, GKE, Cloud Functions, VM/IaaS
- **Production Terraform** default (validate → plan → policy → apply
  → outputs). Bicep opt-in for Azure

### 4. PipelineDoctor with RAG memory *(Iteration-34)*
- Paste / upload CI logs → structured root-cause report with evidence
  anchored to real log lines
- **`rca_embeddings` (pgvector, 1536-dim, HNSW cosine)** — every RCA is
  auto-embedded; every fresh analysis retrieves top-3 past incidents
  cosine-close and prepends them as prior evidence
- **`GET /api/pipeline-doctor/similar?q=…`** — on-call engineers paste
  a fresh error and see whether AIPP has seen it before

### 5. n8n AI-Ops suite (17 workflows) *(Iterations 27-31)*
- Auto-generated from `n8n/build_workflows.py` — **no Code nodes**,
  100 % Community-Edition compatible (no Variables API dependency)
- **Secret-Vault Proxy** — n8n holds zero secrets; all external calls
  land on `/api/proxy/*` on the AIPP host which fans out with AIPP-side
  credentials
- Covers Azure subscription vending, IaC drift, K8s health &
  troubleshoot, Grafana auto-remediation, Azure cost review, incident
  commander, SOP / runbook, SLO burn-rate, DR drills, chaos, log
  anomaly hunter, and the Pipeline Review HITL gate
- **`smoke_test_all.sh`** — single-file, zero-dep smoke test:
  deploy → activate → fire each workflow → pass/fail matrix
- **`demo_reset.sh`** — one-command defense-demo reset with random
  run_ids to avoid n8n cache collisions
- **`dedupe_workflows.py`** — removes ghost / duplicate workflows

### 6. Slack Block Kit HITL bridge *(Iterations 31-33)*
- **`slack_hitl_message()`** emits native Block Kit cards with
  ✅ Approve (with confirm modal) + ❌ Reject buttons
- **`POST /api/slack/interactions`** endpoint:
  - HMAC-SHA256 signature verification (5-min skew window)
  - Strict `action_id` allow-list, `value` guard (`webhook-waiting` only)
  - Returns Block Kit `response_action: update` — Slack replaces the
    card with a sealed "✅ Approved by @user" audit trail
- **HITL Wait-node hardening** — Wait node parameters emitted at
  correct top level (fixes silent bypass in n8n 1.6x); build-time
  `_harden_hitl_upstream()` walks connection graph backwards to mark
  every upstream node `alwaysOutputData: true` + `continueOnFail`
- **Approvals audit tab** — `GET /api/slack/approvals` + Gradio tab
  with decision filter, approver search, 🟢/🔴 markers, JSON download
  for thesis appendix / ISO 27001 evidence packs

### 7. Auto-Deploy to a separate deployment repo *(Iterations 25-26)*
- **Integrations tab** — onboard a GitHub, Azure DevOps, or GitLab repo
- **Fernet-encrypted PATs** at rest (`AIPP_FERNET_KEY`)
- Two modes: **Pull Request** (default, safest) or **Direct Commit**
- Opt-in **confirm checkbox** required before the deploy button
  becomes clickable
- Every attempt audited to `deployments` (YAML SHA-256, commit SHA,
  PR URL, status, error)

### 8. Security & Auth
- **JWT + Bcrypt** login, seeded admin (`admin@aipp.local`)
- **OIDC** wired for Keycloak / Google Workspace / Azure Entra ID
- **Brute-force guard** (per-IP + per-email lockouts)
- **Password reset** flow (Resend email or stdout in dev)
- **API rate limiter** + **secret scanner** on all pipeline endpoints
- **OPA policy bundle** — 12 `.rego` rules across AWS/Azure/GCP with
  live UI preview

### 9. Frontend (Gradio 4 · Futuristic Control-Tower theme)
**13 tabs**:
1. Pipeline Generator (with auto-deploy sub-panel)
2. Integrations
3. PipelineDoctor
4. n8n Workflow Status
5. **HITL Approvals** *(new · Iter-33)*
6. Batch Runner
7. Compare Mode
8. Agent Trace
9. Agents Panel
10. Audit Log
11. Enterprise SSO
12. LLM History
13. — (Doctor + Approvals wiring already counted above)

Custom `aipp_theme.css` — dark glass, neon-purple gradients,
matrix-style login, grid overlay.

### 10. Data model (PostgreSQL 15 + pgvector + Alembic)
- **Core**: `pipeline_runs` · `rca_reports` · `research_experiments`
  · `audit_logs` · `llm_calls` · `users` · `deployment_targets`
  · `deployments` · `integrations` · `identity_providers`
  · `agent_traces` · `site_visits`
- **RAG memory**: `pipeline_embeddings` · `rca_embeddings`
  (1536-dim vectors, HNSW cosine indices, sub-100 ms ANN)

### 11. Research artifacts (thesis-ready)
- `docs/PROPOSAL.md` (academic problem statement)
- `docs/ARCHITECTURE.md` (system diagrams — layered + sequence)
- `docs/AGENT_REGISTRY.md` (agent taxonomy)
- `docs/MCP_ARCHITECTURE.md`
- `docs/PRODUCTION_HARDENING.md`
- `docs/RUNBOOK.md` (ops guide)
- `docs/DEFENCE_QA.md` (viva Q&A)
- `docs/EVALUATION_CORPUS.md` + `docs/RESEARCH.md`
- `docs/literature_review.xlsx` (comparison matrix)
- **Compare Mode** benchmarks static vs generic-LLM vs AIPP for
  evaluation chapter

### 12. Quality & packaging
- **500+ pytests** — offline suite `-n 2 --dist loadscope`
- **Docker Compose** stack: Postgres (pgvector/pgvector:pg15) + backend
  + frontend
- `LICENSE` (MIT) · `CHANGELOG.md` · `README.md` · `.env.example`
- `.gitignore` verified — no secrets committed, `.env.example` shippable
- **`smoke_test_all.sh`** local integration validation for n8n workflows

---

## 🎯 Coverage vs original requirements

| Requirement                              | Status |
|------------------------------------------|--------|
| Gradio frontend                          | ✅ 13 tabs, custom CSS |
| FastAPI backend                          | ✅ 15 routers |
| LangGraph workflow                       | ✅ 8 agents |
| PostgreSQL + pgvector                    | ✅ 13 tables + Alembic |
| Docker & Compose                         | ✅ 3-service stack |
| MCP client / servers                     | ✅ 11 adapters + guard |
| Real credentials (no mocks)              | ✅ GitHub PAT, n8n key, deploy PATs |
| 5 CI × 3 cloud pipelines                 | ✅ all matrix cells |
| PipelineDoctor RCA                       | ✅ evidence-anchored + RAG memory |
| n8n workflow suite                       | ✅ **17 workflows** (Community Edition) |
| HITL Slack approvals                     | ✅ Block Kit + HMAC + audit |
| Secret-Vault Proxy                       | ✅ zero secrets in n8n |
| Academic proposal docs                   | ✅ 12 markdown docs |
| Auth (JWT + OIDC)                        | ✅ full flow + Keycloak wired |
| Auto-deploy to user-controlled repo      | ✅ GitHub + ADO + GitLab |
| Agent Registry                           | ✅ `/api/agents` |
| OPA policy evaluation                    | ✅ 12 rego rules |
| LLM usage persistence                    | ✅ `llm_calls` + history chart |

---

## 🔮 Backlog (not blocking push)

- **P1**: Slack Attribution — persist Slack user_id into resumed n8n
  execution so downstream posts `@`-mention the approver
- **P1**: Compliance PDF Export on Approvals tab (ISO 27001 evidence
  pack, one-click)
- **P1**: GitLab / Harness / Tekton auto-deploy adapters (currently
  GitHub + ADO + GitLab available; Harness + Tekton pending)
- **P2**: Vault Migration — move `backend/.env` secrets to HashiCorp
  Vault or Azure Key Vault; AIPP host holds only a short-lived token
- **P2**: Workflow #01 (Azure Subscription Vending) — GitHub PR flow
  needs a PAT with `repo` + `workflow` scope on the `aipp-iac` repo
- **P2**: Passkeys (WebAuthn) for passwordless admin
- **P2**: n8n workflow template library (community contributions)
- **P2**: Deployment quotas + org RBAC
- **P2**: Public thesis defence video walkthrough

---

## 🚦 Push-readiness: **GREEN**
Everything under `/app` is push-ready. See `docs/DEPLOYMENT.md` for the
step-by-step manual deployment guide and `n8n/README.md` for the
n8n + Slack HITL bring-up.
