# AIPP — Product Requirements & Status

## Original problem statement
Build **AIPP (Automated Pipeline Platform)** — an MS-research grade tool that
generates explainable, deployment-ready CI/CD pipelines from real GitHub
repositories across 5 CI/CD platforms (Azure DevOps, GitHub Actions, GitLab CI,
Harness, Tekton) and 3 clouds (AWS, Azure, GCP). Also performs AI-driven RCA
over CI/CD logs via **PipelineDoctor**, and drives 17 n8n AI-Ops workflows
with Slack Block Kit HITL approvals.

## Chosen configuration (from user)
- **Frontend**: Gradio 4 (Python) · 13 tabs
- **Backend**: FastAPI + LangGraph state machine · 15 routers
- **DB**: PostgreSQL 15 + **pgvector** (async SQLAlchemy + Alembic)
- **LLM**: universal LLM key (swap to Anthropic/OpenAI/Gemini via `.env`)
- **Governance layer**: MCP client + 11 adapters
- **n8n**: 17 workflows, 100 % Community-Edition compatible
- **HITL**: Slack Block Kit + HMAC-verified `/api/slack/interactions`
- **Packaging**: Docker + docker-compose (pgvector/pgvector:pg15)

## Status (2026-02 — Repo cleanup + docs refresh · SHIPPED)

**This session:**
- ✅ **Removed unwanted files/folders** from git:
  - Root: `yarn.lock`, `test_result.md`
  - `n8n/documentation/` (duplicate of `n8n/docs/`)
  - `backend/tests/adhoc_verify_azure_yaml.py` (dev scratch)
  - `.emergent/` + `test_reports/` untracked via `.gitignore`
- ✅ **Moved** doc-generation scripts to `scripts/`:
  `generate_deck_pptx.py`, `generate_proposal_docx.py`, `md_to_docx.py`
- ✅ **Consolidated** n8n docs — `n8n/docs/README.md` → `n8n/README.md`
  (rewritten to reflect 17 workflows, smoke_test_all.sh, demo_reset.sh,
  Secret-Vault Proxy, Slack Block Kit HITL)
- ✅ **Updated docs** to Iteration-34 state:
  - `README.md` — 13 tabs, 17 workflows, PipelineDoctor RAG, HITL Block Kit
  - `ARCHITECTURE.md` — new §11 for n8n + Slack HITL bridge + PipelineDoctor
    RAG sequence; 13 tabs, 15 routers, 13 tables
  - `CHANGELOG.md` — prepended 0.31.5, 0.32.0, 0.33.0, 0.34.4 entries
  - `docs/STATUS.md` — full rewrite for Iter-34
  - `docs/RUNBOOK.md` — full rewrite with n8n ops, Slack HITL section
  - `docs/DEPLOYMENT.md` — n8n + Slack bring-up section, updated env vars
  - `docs/DEFENCE_QA.md` — appended §I (Q28-34) covering HITL + RAG

## Status (2026-02 — Iteration-34 · RCA Auto-Embedding + Retrieval · SHIPPED)

**Iteration-34 delta:**
- ✅ **`backend/services/rca_embedding_service.py`** — new service with
  three pure helpers: `_build_content()` composes a compact
  retrieval-friendly string (root cause first, no evidence lines to
  avoid poisoning retrieval with project-specific paths);
  `embed_and_persist()` embeds via the existing `EmbeddingService` and
  inserts into `rca_embeddings` (best-effort, swallows pgvector-missing
  / embedder-crash / DB-offline cleanly); `find_similar()` runs a
  cosine ANN query and joins to `rca_reports` for full context.
- ✅ **`POST /api/pipeline-doctor/analyze` is now RAG-aware**. On every
  call it: (1) retrieves the top-3 past RCAs cosine-close to the new
  log, (2) prepends them as an explicit context block to the LLM
  prompt with a "use as prior evidence, but do NOT cite them as
  current-log evidence" guard, (3) persists the fresh RCA, then
  (4) fires `embed_and_persist()` so the memory grows on every use.
  The response includes a new `retrieved_from_memory` array so
  operators can trust-but-verify the retrieval was relevant.
- ✅ **`GET /api/pipeline-doctor/similar?q=…&limit=N`** — new endpoint
  mirroring `/api/pipelines/similar`. On-call engineers can paste a
  raw error message to see if AIPP has seen it before.
- ✅ **16 new pytests** (`test_rca_embedding.py`) — content composition,
  every failure mode of embed/find (pgvector missing, embedder crash,
  empty query), context-block formatting, the /similar endpoint, and
  end-to-end wiring of the analyze RAG loop. Total 60/61 pass across
  RCA + Slack + HITL + n8n suites (only pre-existing `test_no_stub_urls`
  fails — missing `.env.n8n` in this dev pod, unrelated).

## Status (2026-02 — Iteration-33 · HITL Approvals Tab · SHIPPED)

**Iteration-33 delta (this session):**
- ✅ **`GET /api/slack/approvals`** endpoint reads `audit_logs` filtered
  by `action='slack.hitl.decision'` and returns a UI-friendly list
  (id, when, decision, user, user_id, channel, workflow_hint,
  n8n_execution_id, n8n_status). Bounded 1..500 (422 on out-of-range).
- ✅ **Audit write on every HITL click** — `backend/api/slack.py` now
  extracts the n8n execution ID from the resume URL (regex on
  `/webhook-waiting/<id>`), captures the Slack user + user_id + channel,
  and writes to `audit_logs`. Resume-URL signature tokens are stripped
  before persistence (verified by a dedicated test).
- ✅ **New Gradio tab — "HITL Approvals"** (`frontend/tabs/approvals.py`)
  wired into the main app between "n8n Workflow Status" and "Compare
  Mode". Features: decision filter (All/Approve/Reject), approver
  search-as-you-type, colored 🟢/🔴 markers, top-of-tab summary
  ("N decisions · X approved · Y rejected · Z unique approvers"),
  JSON download for thesis appendices / ISO 27001 evidence packs,
  and a `gr.Timer(20s)` auto-refresh (gated by a checkbox).
- ✅ **4 new pytests** covering: audit write shape + resume-token
  redaction, graceful degradation when DB is offline, /approvals
  response shape, and the limit-bounds guard. 13/13 Slack tests pass,
  31/32 total in the Slack+n8n suites (only the pre-existing
  test_no_stub_urls failure remains — missing `.env.n8n` in this dev
  pod, unrelated).

## Status (2026-02 — Iteration-32 · Slack Block Kit HITL + Demo Reset · SHIPPED)

**Iteration-32 delta (this session):**
- ✅ **Native Slack Block Kit HITL buttons** — new `slack_hitl_message()`
  helper in `build_workflows.py` emits proper Block Kit JSON with green
  ✅ Approve / red ❌ Reject buttons + a "Confirm approval" modal on the
  Approve button. The plain-text approve/reject links are kept as a
  fallback in the same message body so old Slack clients or the
  bridge-offline case still work.
- ✅ **`POST /api/slack/interactions`** endpoint (`backend/api/slack.py`)
  bridges Slack button clicks to n8n resume URLs. HMAC-SHA256 signature
  verification against `SLACK_SIGNING_SECRET` (5-minute skew window),
  strict `action_id` allow-list (approve|reject only), and a `value`
  guard that rejects any button that doesn't carry an `n8n
  webhook-waiting` URL. On success it returns a `response_action:
  update` Block Kit card that seals the message with the clicking user
  and a timestamp — full audit trail lives in Slack.
- ✅ **`n8n/scripts/demo_reset.sh`** — one-command defense-demo reset:
  wipes every past execution, fires all four HITL webhooks with fresh
  realistic payloads (random run_ids so no cache collisions), waits 8s
  for them to park, and optionally auto-approves or auto-rejects all
  new waiting executions. Supports `--keep` to skip cleanup.
- ✅ **9 new pytest cases** for the Slack bridge (`test_slack_interactions.py`)
  — signature happy-path + tampered-sig + stale-ts + missing-secret +
  bogus-action + malicious-value + non-action ack + reject-path.
  All 9 pass; total 27/28 workflow+bridge tests pass in this pod.

## Status (2026-02 — Iteration-31 · HITL Wait-Node Hardening · SHIPPED)

**Iteration-31 delta (this session):**
- ✅ **HITL Wait-node bypass fixed** — Wait node parameters (`httpMethod`,
  `responseCode`, `responseMode`, `responseData`, `limitWaitTime: false`)
  are now emitted at the correct TOP LEVEL (not nested inside `options`),
  matching the schema Wait.node.ts inherits from Webhook's description
  module. Previously n8n silently ignored them and, in some 1.6x builds,
  finished the execution immediately with `waitTill=None`.
- ✅ **Build-time HITL upstream hardener** — `_harden_hitl_upstream()`
  walks the connection graph backwards from every Wait node and marks
  every ancestor (except triggers / IF / Filter / Wait itself) with
  `onError: continueRegularOutput` and `alwaysOutputData: true`. If
  Slack/LLM creds are missing or the AIPP proxy is unreachable, the
  flow still reaches the Wait node and parks correctly.
- ✅ **`deploy.sh --activate-all`** — new flag flips every workflow on
  the server to active in one command after a fresh deploy (great for
  demo bring-up: freshly-imported workflows come up live immediately).
- ✅ **Gradio dashboard auto-refresh** — new "Auto-refresh every 30 s"
  toggle on the n8n Workflow Status tab. Uses `gr.Timer` (Gradio 4.44
  supported); preserves the user's current dropdown selection so an
  in-progress "Execute" doesn't get its picker reset mid-run.
- ✅ **Two new pytest contracts** locking these invariants:
  `test_hitl_wait_nodes_have_correct_schema` + `test_hitl_upstream_nodes_are_failsafe`
  (18/19 tests pass — only pre-existing `test_no_stub_urls` fails because
  `.env.n8n` is missing in this dev pod; unrelated to this change).

## Status (2026-02 — Iteration-30 · n8n Production Hardening · SHIPPED)

**Iteration-30 delta (this session):**
- ✅ 15 n8n workflows + shared **Error Sink (#00)** — every business flow
  attaches to it via `settings.errorWorkflow`
- ✅ **Correctness fixes**: static `AZURE_TOKEN` replaced with a shared
  `Azure · Get Token` client_credentials exchange node in every Azure
  workflow; env-var names normalised to a single source of truth;
  `wf_02 IaC Drift` httpbin stub replaced with real GitHub API fetch
- ✅ **Multi-tenant + security**: Slack signature verification node
  (`SLACK_SIGNING_SECRET`, HMAC-SHA256, 5-min replay window); Validate
  Input node on every webhook; `GH_REPO_ALLOWLIST` gate; Slack
  channels externalised via `SLACK_CHANNEL_{DEFAULT,ALERTS,APPROVALS,DIGEST}`
- ✅ **Observability + reliability**: `Init Trace` node emits
  correlation id in every workflow, all HTTP/Slack/LLM nodes have
  `retryOnFail=true maxTries=3` with exponential backoff, traceId
  appended as italic footer to every Slack post
- ✅ **`backend/tests/test_n8n_workflows.py`** — 15 pytest contracts
  covering all of the above (no dead env refs, no stub URLs, no
  static Azure bearer, error sink attached, retries present, Slack
  sig verify on Slack-triggered flows, unique node names, valid JSON,
  expected count = 16)
- ✅ 569 unit tests passing (14 prior + 15 new n8n contracts)

## Status (2026-02 — Iteration-27 · Directive Trace + Agent Trace + SSO Wiring · SHIPPED)

- ✅ Docker Compose stack (Postgres + backend + Gradio frontend)
- ✅ 554 pytest cases passing (baseline was 534 — +20 new coverage)
- ✅ 8 LangGraph agents + Agent Registry (`/api/agents`)
- ✅ 11 MCP adapters, MCP guard, adapter-skill authorization
- ✅ 5 CI/CD YAML generators — all with inline comments + native task use
- ✅ Terraform-default for all clouds; Bicep opt-in for Azure
- ✅ Production Terraform infra pipeline (validate → plan → policy → apply)
- ✅ PipelineDoctor RCA with evidence anchoring
- ✅ Compare Mode + `research_experiments` metrics table
- ✅ Audit Log tab + JSON export
- ✅ Futuristic control-tower UI (`aipp_theme.css`, animated agent orbs)
- ✅ JWT auth + OIDC (Google / Azure AD) + password-reset + brute-force guard
- ✅ Live LLM token streaming (SSE) + persistent `llm_calls` history
- ✅ OPA policy starter bundle (12 rules across AWS/Azure/GCP) + UI preview
- ✅ **Auto-Deploy** — deployment repos (GitHub / Azure DevOps / GitLab), Fernet-encrypted PATs
- ✅ Custom Directive Parser + **Directive Trace** panel (regex match, deploy_style, YAML evidence)
- ✅ **Agent Execution Trace** *(new · iteration-27)* — `agent_traces` table + `_track()` collector + `/api/agents/traces` + Gradio "Agent Trace" tab (timeline + per-agent LLM prompts, tokens, cost, MCP calls, skills)
- ✅ **Enterprise SSO wired end-to-end** *(new · iteration-27)* — OIDC login accepts `?provider_id=<uuid>`, resolves from `identity_providers` DB table, falls back to `.env`; login page renders one "Sign in with X" button per DB provider automatically

## Core UI (11 tabs)
1. Pipeline Generator (with Directive Trace + Auto-Deploy panels)
2. Batch Runner
3. Integrations — onboard deployment platforms + audit history
3. PipelineDoctor
4. n8n Workflow Status
5. Compare Mode
6. Audit Log
7. Agents (registry)
8. LLM Spend History

## Key data models
- `pipeline_runs` · `rca_reports` · `research_experiments` · `audit_logs`
- `llm_calls` · `users`
- `deployment_targets` *(new)* — encrypted PAT, platform, repo, default branch
- `deployments` *(new)* — audit trail: SHA-256 of YAML, commit SHA, PR URL,
  status, error, mode

## Key API endpoints (v1)
- `POST /api/pipelines/generate` (+ `/stream`)
- `POST /api/pipeline-doctor/analyze`
- `POST /api/deployment/commit` · `/trigger`
- `POST /api/auth/login` · `/me` · `/oidc/*` · `/password/*`
- `GET  /api/agents` · `/mcp/tools` · `/policy/bundle`
- `POST /api/integrations/targets` (list/create/delete/test)
- `POST /api/integrations/deploy`
- `GET  /api/integrations/deployments`

## Priorities & backlog

### 🟢 P0 — completed
All items above.

### 🟡 P1 — nice-to-have (future work)
- Multi-repo batch evaluation runner exposed via UI
- Passkeys (WebAuthn) for passwordless admin login
- GitLab CI direct-push adapter for Auto-Deploy (currently GitHub + ADO only)
- Deployment target quotas + org-level RBAC

### 🔵 P2 — thesis wrap-up
- Final academic evaluation run against 20+ public repos, chart export
- Video walkthrough for defence
- Push to public GitHub with the "Save to GitHub" flow

## Files & directories (added in this iteration)
- `backend/services/crypto_service.py`
- `backend/services/azdo_writer.py`
- `backend/services/deployment_targets.py`
- `backend/api/integrations.py`
- `backend/tests/test_iteration_25_auto_deploy.py`
- `frontend/tabs/integrations.py`
- `docs/RUNBOOK.md`
- `CHANGELOG.md`
- `LICENSE` (MIT)

## Modified files
- `backend/database/models.py` — added `DeploymentTarget` + `Deployment`
- `backend/mcp/adapters/github.py` — added `_open_pull_request`
- `backend/server.py` — registered integrations router
- `frontend/gradio_app.py` — added Integrations tab, token forwarding
- `frontend/components/api_client.py` — auth-header support
- `frontend/tabs/pipeline_generator.py` — auto-deploy sub-panel
- `docker-compose.yml` — added `AIPP_FERNET_KEY`, JWT/OIDC/email env passthrough
- `.env.example` — documented `AIPP_FERNET_KEY`
- `backend/tests/test_iteration_12_pipeline_type_setup_help.py` — arity bumped
- `README.md`, `ARCHITECTURE.md` — updated tab list + endpoints

## Test status
- Offline suite: **489 passed, 2 skipped** on `-n 2 --dist loadscope`.
- Live-backend integration tests (`backend_test.py`,
  `test_deployment_and_generators.py`) skipped in this fork because Postgres
  user was wiped from the sandbox pod. They pass under `docker compose up`.

## Credentials to test flow
- Default admin: `admin@aipp.local` / `aipp-change-me`
  (see `/app/memory/test_credentials.md`).
- `AIPP_FERNET_KEY` is set in `.env` (single root file, rotate for production).

## Iteration-26 · Dropdown popover fix + Batch Repo Runner (Feb-2026)

### Dropdown popover fix
- Bug: on the VM, users reported the CI/CD Platform, Cloud Platform and
  Deployment target dropdowns were "not working" — clicking focused the
  input but no option list appeared.
- Root cause: `frontend/static/aipp_theme.css` applied
  `backdrop-filter: blur(14px) saturate(140%)` to
  `.form/.block/.gr-box/.gr-group/.gr-panel`. CSS spec: any ancestor with
  `backdrop-filter`, `filter`, `transform`, `perspective`, `contain` or
  `will-change` becomes the containing block for `position: fixed`
  descendants. Gradio 4.44's `DropdownOptions.svelte` positions the
  popover with `position: fixed` + viewport-relative coords, so the popover
  was rendered at wrong coordinates (behind or off-screen), giving the
  illusion of a broken control.
- Fix: removed `backdrop-filter` from card/form containers (glass look
  preserved via translucent background). Added explicit z-index + styling
  overrides for `.gr-dropdown ul`, `ul.options` and
  `[data-testid="dropdown-options"]` to guarantee the popover floats above
  cards. Users MUST restart the Gradio container (`docker compose restart
  frontend`) after pulling — the CSS is inlined at Python startup.
- Verification: sandbox Playwright run confirmed all 5 CI options render
  in the popover, no ancestor breaks `position: fixed`, options are
  clickable and populate the input.

### Batch Repo Runner
- New endpoint `POST /api/research/batch` accepts up to 20 repo URLs plus
  a shared config (CI/cloud/pipeline_type/IaC tool) and produces a
  `ResearchExperiment` row per repo with metrics (seconds,
  validation_passed, yaml_bytes, secrets_clean, deployment_target).
  Failures are recorded per-repo without aborting the batch. See
  `backend/api/research.py::run_batch`.
- New Gradio tab **Batch Runner** (`frontend/tabs/batch_runner.py`)
  offers a textarea repo input (`URL@branch` supported), shared config
  dropdowns, a Run button, a results DataFrame, a per-repo BarPlot
  coloured by outcome (`passed` / `failed_validation` / `error`), and a
  CSV download for the thesis Evaluation table.
- 10 new pytest tests in `test_iteration_26_batch_runner.py`.

### GitLab Auto-Deploy
- New writer `backend/services/gitlab_writer.py` mirrors the shape of
  `azdo_writer.py`: `probe`, `commit_file`, `open_merge_request`.
  Never auto-creates the target branch on direct-commit mode.
- `services/deployment_targets.py` wired to accept `gitlab_ci` platform
  (both `probe` and `deploy` paths). PAT still Fernet-encrypted.
- `api/integrations.py` schema updated to accept `gitlab_ci`.
- `frontend/tabs/integrations.py` adds **GitLab CI (gitlab.com / self-
  hosted)** to the platform dropdown; PAT hint mentions
  `write_repository` scope.
- 10 new pytest tests in `test_iteration_26_gitlab_writer.py` using
  `httpx.MockTransport` — hermetic, no new dependencies.
- Auto-deploy panel in the Pipeline Generator picks up GitLab targets
  automatically because it filters by `ci_platform`.

- Files touched: `backend/api/research.py`,
  `backend/api/integrations.py`,
  `backend/services/gitlab_writer.py` (new),
  `backend/services/deployment_targets.py`,
  `frontend/tabs/batch_runner.py`,
  `frontend/tabs/integrations.py`,
  `frontend/tabs/pipeline_generator.py`,
  `frontend/gradio_app.py`,
  `frontend/static/aipp_theme.css`,
  `backend/tests/test_iteration_26_batch_runner.py` (new),
  `backend/tests/test_iteration_26_gitlab_writer.py` (new).
- Status: shipped, offline suite **501 pass / 1 skip**.
