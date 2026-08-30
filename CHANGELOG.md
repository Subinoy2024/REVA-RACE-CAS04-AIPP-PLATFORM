# Changelog

All notable changes to **AIPP — Automated Pipeline Platform**. This project
adheres to [Semantic Versioning](https://semver.org/) and the
[Keep a Changelog](https://keepachangelog.com/) format.


## [0.37.1] — 2026-08-28 · Live Infrastructure Discovery & Real-Time PostgreSQL Sync

### Added & Improved
- **Real-Time PostgreSQL Database Sync (`POST /api/workflows/rca/docx`)**: Updated post-mortem generator endpoint to immediately persist all generated incident reports into `rca_reports`, record audit events in `audit_logs`, and embed searchable incident vectors into `rca_embeddings` with pgvector similarity indexing.
- **Direct Backend Workflow Wiring**: Wired Workflow 11 (`Generate .DOCX Runbook`) to make dynamic `POST /api/workflows/rca/docx` requests to the AIPP backend, guaranteeing 1:1 synchronization between n8n executions and backend database records.
- **Dynamic Live Kubernetes Discovery**: Implemented `discover_live_k8s_infra()` across test and demo scripts (`test_all_workflows_chaos.py`, `demo_suite.py`) to query live running pods in namespace `aipp` via `kubectl` and inject real cluster telemetry.

## [0.37.0] — 2026-08-28 · Topic-Aware & Severity-Gated SOP / Runbook Generation

### Added & Improved
- **Topic-Aware Incident Context Extraction (`11_sop__runbook_generator`)**: Added context extraction node parsing incident titles, Grafana Alertmanager metrics (`commonLabels.alertname`), impacted services/pods, and root cause summaries.
- **SRE Severity Gating**: Configured `Critical or Closed?` IF condition to automatically generate full `.docx` post-mortems for Critical / P1 / Sev-1 incidents and closed post-mortems, while routing transient / non-critical alerts to lightweight notifications to avoid document fatigue.
- **Enhanced Slack Review Notifications**: Formatted Slack notifications with explicit incident topic, impacted service, severity badge, and root cause summary.
- **`if_equals_node` Expression Fix**: Fixed curly bracket escaping in `build_workflows.py` ensuring exact `={{ ... }}` n8n expression evaluation across all conditional nodes.

## [0.36.0] — 2026-08-27 · 20 n8n Workflows & Grafana Auto-Remediator Verification

### Verified & Added
- **Grafana Observability Auto-Remediator (`08_grafana_observability_autoremediator`)**: Live Grafana Alertmanager webhook integration (`POST /webhook/aipp-grafana`) verified with LLM metric diagnosis, automated kubectl fix proposals (`restart_pod`), and Slack `#aipp` Human-in-the-Loop (HITL) approval / rejection decision gates.
- **20 n8n Workflows Build & Deploy**: Rebuilt and activated all 20 workflows (`00_error_sink` through `19_azure_network_watcher_audit`) on `https://n8n.dccloud.in.net` via `n8n/scripts/deploy.sh --activate-all`.
- **Portable Deploy Script**: Fixed `mapfile` compatibility in `n8n/scripts/deploy.sh` for macOS / BSD bash environments.
- **SRE Chaos Test Harness**: Updated `scripts/test_all_workflows_chaos.py` with 1:1 trigger paths and required form payload schemas; achieved **20/20 HTTP 200 PASS rate**.
- **Unit Test Invariants**: Fixed expected workflow count assertion in `backend/tests/test_n8n_workflows.py` (`19/19 PASSED`).

## [0.35.0] — 2026-08-25 · Phase 0 · K8s Deployment & Authentication Verification

### Verified
- **Phase 0 Completed**: Successfully deployed and authenticated on the local Kubernetes cluster (`aipp` namespace).
- Admin authentication verified on `http://aipp.dccloud.com` with `admin@dccloud.in.net`.
- K8s services (`aipp-backend`, `aipp-frontend`, `aipp-postgres`) operational and healthy.

## [0.34.4] — 2026-02 · Iteration-34 · PipelineDoctor RAG · auto-embed + retrieve

### Added
- **`backend/services/rca_embedding_service.py`** — new service with
  three helpers:
  - `_build_content()` composes a compact retrieval-friendly string
    (root cause first; evidence lines omitted to avoid poisoning
    retrieval with project-specific paths).
  - `embed_and_persist(rca_id, report_json)` embeds via
    `EmbeddingService` and inserts into `rca_embeddings`; swallows
    pgvector-missing / embedder-crash / DB-offline cleanly.
  - `find_similar(query_text, limit=3)` runs cosine ANN via pgvector
    `<=>` and joins to `rca_reports` for full context.
- **`POST /api/pipeline-doctor/analyze` is now RAG-aware.** Every call:
  1. embeds a compact query (incident_context + first ~2 KB of log),
  2. retrieves top-3 past RCAs cosine-close via `find_similar()`,
  3. prepends them as a "prior evidence, do NOT cite" context block,
  4. persists the fresh RCA, then
  5. fires `embed_and_persist()` so memory grows on every use.
  Response includes `retrieved_from_memory[]` so operators can
  trust-but-verify.
- **`GET /api/pipeline-doctor/similar?q=…&limit=N`** — mirrors
  `/api/pipelines/similar` but hits `rca_embeddings × rca_reports`.
  On-call engineers paste a raw error and see if AIPP has seen it.

### Added — tests
- **`backend/tests/test_rca_embedding.py`** — 16 pytests: content
  composition, every failure mode of embed/find (pgvector missing,
  embedder crash, empty query), context-block formatting, `/similar`
  endpoint contract, end-to-end wiring of the analyse RAG loop.


## [0.33.0] — 2026-02 · Iteration-33 · HITL Approvals Audit Tab

### Added
- **`GET /api/slack/approvals`** — reads `audit_logs WHERE
  action='slack.hitl.decision'`; returns flat UI-friendly rows (id,
  when, decision, user, user_id, channel, workflow_hint,
  n8n_execution_id, n8n_status). Bounded 1..500 (422 on out-of-range).
- **Audit write on every HITL click** — `backend/api/slack.py` extracts
  the n8n execution ID from the resume URL (regex `/webhook-waiting/(\d+)`),
  captures Slack user + user_id + channel, and writes to `audit_logs`.
  **Resume-URL signature tokens stripped** before persistence (verified
  by a dedicated test — no short-lived tokens leak into the audit trail).
- **New Gradio tab — HITL Approvals** (`frontend/tabs/approvals.py`)
  between "n8n Workflow Status" and "Compare Mode". Features:
  decision filter (All / Approve / Reject), approver search-as-you-type,
  🟢/🔴 markers, summary line ("N decisions · X approved · Y rejected ·
  Z unique approvers"), JSON download for thesis appendix / ISO 27001
  evidence packs, and a `gr.Timer(20s)` auto-refresh (checkbox gated).

### Added — tests
- **4 new pytests** in `test_slack_interactions.py`: audit-write shape,
  resume-token redaction, DB-offline degradation, `/approvals` limit
  bounds guard.


## [0.32.0] — 2026-02 · Iteration-32 · Slack Block Kit HITL + Demo Reset

### Added — Native Slack Block Kit HITL buttons
- **`slack_hitl_message()` helper in `build_workflows.py`** — emits Block
  Kit JSON with:
  * ✅ Approve (`style: primary`) + confirm modal ("This will resume the
    parked n8n execution and apply the proposed change. Continue?").
  * ❌ Reject (`style: danger`).
  * Fallback plain-text approve/reject links kept in the same message
    for old Slack clients or the bridge-offline case.
- **`POST /api/slack/interactions`** endpoint (`backend/api/slack.py`) —
  bridges Slack button clicks to n8n resume URLs:
  * HMAC-SHA256 verification against `SLACK_SIGNING_SECRET` (5-min skew).
  * Strict `action_id` allow-list (`approve` | `reject` only).
  * `value` guard: rejects any button not carrying `webhook-waiting`.
  * Returns Block Kit `response_action: update` that seals the message
    with the clicking user + timestamp — full audit trail in Slack.
- **`n8n/scripts/demo_reset.sh`** — one-command defense-demo reset:
  wipes past executions, fires all 4 HITL webhooks with fresh realistic
  payloads (random run_ids → no cache collisions), waits 8 s for parking,
  and optionally auto-approves/rejects. `--keep` skips cleanup.

### Added — tests
- **`backend/tests/test_slack_interactions.py`** — 9 pytests: signature
  happy-path, tampered sig, stale timestamp, missing secret, bogus
  action_id, malicious `value`, non-action ack, reject-path resume.


## [0.31.5] — 2026-02 · Iteration-31 · HITL Wait-Node Hardening + Deploy UX

### Fixed
- **HITL Wait-node bypass fixed** — Wait node parameters (`httpMethod`,
  `responseCode`, `responseMode`, `responseData`, `limitWaitTime: false`)
  now emitted at the correct TOP LEVEL (not nested inside `options`),
  matching the schema `Wait.node.ts` inherits from Webhook's description
  module. Previously n8n silently ignored them and, in some 1.6x builds,
  finished executions immediately with `waitTill=null`.
- **Build-time HITL upstream hardener** — `_harden_hitl_upstream()`
  walks the connection graph backwards from every Wait node and marks
  every non-trigger ancestor with `onError: continueRegularOutput` +
  `alwaysOutputData: true`. If Slack/LLM creds are missing or the AIPP
  proxy is unreachable, the flow still reaches the Wait node and parks.

### Added
- **`deploy.sh --activate-all`** — flips every workflow on the n8n
  server to active in one command after a fresh deploy.
- **Gradio dashboard auto-refresh** — "Auto-refresh every 30 s" toggle
  on the n8n Workflow Status tab. Uses `gr.Timer` (Gradio 4.44+);
  preserves the user's dropdown selection.
- **`n8n/scripts/smoke_test_all.sh`** — single-file, 470-line, zero-dep
  script that deploys, activates, and fires every workflow with the
  right trigger (webhook / form / schedule / error), waits 12 s, and
  prints a colour-coded pass/fail matrix + AIPP `/health` snapshot.
- **`n8n/scripts/dedupe_workflows.py`** — removes ghost / duplicate
  workflows from n8n (keeps the highest-numbered ID per canonical name).


## [0.34.0] — 2026-02 · Iteration-34 · pgvector RAG · past-failure retrieval

### Added
- **Postgres image** swapped to `pgvector/pgvector:pg15` (docker-compose.yml).
- **Alembic migration `34_pgvector_rag`** — enables `vector` extension,
  creates `pipeline_embeddings` and `rca_embeddings` tables with a 1536-dim
  vector column each + HNSW cosine indices for sub-100ms ANN search.
- **`backend/services/embedding_service.py`** — wraps OpenAI
  `text-embedding-3-small` via the Emergent LLM key. Batch (`embed_many`)
  + async single (`embed`). Deterministic hash fallback keeps tests
  hermetic + demo running when no key is configured.
- **`GET /api/pipelines/similar?q=<text>&limit=5`** — embeds the query,
  runs cosine ANN via pgvector `<=>` operator, returns runs ordered by
  similarity (`1 - distance`). Graceful degradation:
  * pgvector missing → HTTP 501 with clear message
  * table not created yet → returns `{hits: 0, results: []}`
- **Auto-embedding on pipeline generation** — `pipeline_service.generate()`
  now embeds every successful run's `explanation` into
  `pipeline_embeddings`. Best-effort — legacy DBs without pgvector skip
  silently.

### Added — tests
- **`backend/tests/test_rag_pgvector.py`** — 11 pytest contracts:
  * embedding dim = 1536
  * fallback deterministic + unit-normed
  * different inputs → different vectors
  * `embed_many` shape correct
  * `/similar` requires `q`, rejects empty/bad `limit`
  * `/similar` → 501 when pgvector missing (mocked session)
  * `/similar` → `hits: 0` when table not yet created
  * migration file exists with `CREATE EXTENSION` + `hnsw` + both tables
  * docker-compose references `pgvector/pgvector`

### Deploy notes
- **On `keycloak01`** after pulling:
  ```bash
  docker compose down postgres            # gracefully stop
  docker compose pull postgres            # get pgvector image
  docker compose up -d postgres           # start with new image
  # (data volume is preserved — extension enables on first migration)

  # Apply migration
  docker compose exec backend alembic upgrade head
  ```
- Verify: `docker compose exec postgres psql -U aipp -d aipp -c "\dx"`
  → should list `vector`.
- Smoke test:
  ```bash
  curl "https://aipp.dccloud.in.net/api/pipelines/similar?q=aws%20deploy%20failure"
  # → {"query":"...", "hits":0, "results":[]}   (empty until you generate a few pipelines)
  ```



## [0.33.0] — 2026-02 · Iteration-33 · HITL Gate + Real-Alert Bridges

### Added — A · Backend Auto-Trigger with Human-In-The-Loop
- **New workflow `AIPP · 16 · Pipeline Review Gate (HITL)`** — every AIPP
  pipeline generation now fires this webhook. Flow:
  Webhook → Init Trace → Validate Input → `AI · Risk Summary` → Slack
  approval card with copy-paste curl commands for approve / reject.
- **New endpoints** `POST /api/pipelines/{run_id}/approve` and
  `POST /api/pipelines/{run_id}/reject` — bearer-authed via the shared
  proxy key. Approve records the decision AND fans out to `#11 SOP` and
  `#02 IaC Drift` workflows via `n8n_hooks.fire`.
- **`services/pipeline_service.py`** — after every `generate()`, fires
  `pipeline_review` event with `{run_id, target_platform, cloud, repo,
  actor, summary_url}`. Best-effort — n8n outage never breaks
  generation.

### Added — B · Real Alert Bridges
- **New router `backend/api/webhooks.py`** with two inbound handlers:
  * `POST /api/webhooks/grafana` — accepts Grafana Contact-Point
    payload, normalises to `{alerts, commonLabels, commonAnnotations}`,
    forwards to n8n `#08 Grafana Observability Auto-Remediator`.
  * `POST /api/webhooks/azure-monitor` — accepts Azure Common Alert
    Schema, forwards to n8n `#10 Incident Commander Bot`.
- Both endpoints share the `PROXY_API_KEY` bearer.
- Health probe: `GET /api/webhooks/health`.

### Added — tests
- **`backend/tests/test_hitl_and_webhooks.py`** — 12 pytest contracts:
  * workflow #16 exists, has HITL prelude, references approve/reject
    endpoints, uses `$vars.AIPP_BASE_URL`
  * approve/reject require bearer, 401 without
  * Grafana webhook forwards → `fire('grafana_alert', ...)` called once
    with `source='grafana'` and correct alert count
  * Azure Monitor webhook forwards → `fire('incident', ...)` called
  * `n8n_hooks._EVENT_ROUTES` contains `pipeline_review` and `iac_drift`

### Total workflow count: 17 (was 16)
### Total backend endpoints: +5

### How to wire real alerts on your side
* **Grafana** → Alerting → Contact Points → Add → Webhook →
  URL `https://aipp.dccloud.in.net/api/webhooks/grafana` →
  Custom header `Authorization: Bearer $PROXY_API_KEY`.
* **Azure Monitor** → Action Groups → Add → Webhook →
  URL `https://aipp.dccloud.in.net/api/webhooks/azure-monitor` →
  Add custom header (Common Alert Schema toggle: ON).



## [0.32.0] — 2026-02 · Iteration-32 · n8n Variables API (zero-touch n8n)

### Added
- **`n8n/scripts/push_variables.sh`** — pushes every KEY=VALUE from
  `.env.n8n` to the n8n server's `/api/v1/variables` REST API. Idempotent
  (PATCH if key exists, POST otherwise). Uses only `N8N_BASE_URL` +
  `N8N_API_KEY` — **no SSH into the n8n host ever needed**.
- Dry-run mode (`--dry-run`) prints the plan without hitting n8n.

### Changed
- **All workflows now use `{{$vars.KEY}}` instead of `{{$env.KEY}}`** —
  n8n resolves at execution time from its Variables store, meaning
  rotating a secret is a single `push_variables.sh` from the AIPP host.
  No container restart. No file mount. No SSH.
- `n8n/build_workflows.py` — single-line change: default expression prefix
  swapped `$env.` → `$vars.` across 30+ workflow references.
- Test suite tightened — new `test_no_lingering_env_refs` fails the build
  if any workflow ever regresses back to `$env.*`.

### Operational model — end state
```
Rotate a secret / change a channel:
   nano .env.n8n                     # on keycloak01
   bash scripts/push_variables.sh    # pushes over HTTPS, no restart
   done.

Deploy new workflows:
   python build_workflows.py         # regenerate JSONs
   bash scripts/deploy.sh            # push over HTTPS

Never touch the n8n host again for AIPP work.
```



## [0.31.0] — 2026-02 · Iteration-31 · Secret-Vault Proxy (Option 2)

### Added
- **`/api/proxy/*` router** (`backend/api/proxy.py`) — AIPP now acts as the
  secret vault. n8n workflows call these endpoints with a single
  `Authorization: Bearer $env.AIPP_API_KEY` header; AIPP fans the call out
  using its own K8s/GitHub/Proxmox/Grafana/ADO credentials.
- Endpoints: `GET /health`, `GET /k8s/pods{?ns}`, `GET /k8s/pods/{ns}/{name}`,
  `GET /github/repo/{owner}/{repo}`, `GET /github/tree/{owner}/{repo}`,
  `GET /github/org/{org}/members`, `GET /github/runs/{owner}/{repo}`,
  `POST /github/pr`, `GET /ado/runs`, `POST /proxmox/vm`, `GET /grafana/alerts`.
- **Constant-time API-key check** via `hmac.compare_digest`.
- **`GH_REPO_ALLOWLIST` enforcement moved server-side** — a compromised n8n
  cannot bypass the allowlist by editing its own env.
- **`backend/tests/test_proxy.py`** — 13 pytest contracts: auth required,
  wrong key rejected, 503 when infra unconfigured, allowlist blocks unknown
  repos, workflow generator emits proxy calls (no direct `K8S_TOKEN`/
  `GITHUB_PAT`/`PROXMOX_TOKEN` refs remaining).

### Changed
- `n8n/build_workflows.py` — new `aipp_call(name, method, path, body, pos)`
  helper. Workflows #01/#02/#03/#04/#05/#06/#07/#10 refactored to call
  the proxy. Azure workflows (#09/#12/#13/#15) intentionally retain the
  direct OAuth exchange (short-lived tokens; proxying would just add hops).
- `n8n/.env.n8n.example` **dramatically simplified** — infra secrets
  (K8S_TOKEN, GITHUB_PAT, PROXMOX_TOKEN, GRAFANA_API_KEY, ADO_PAT,
  GH_REPO_ALLOWLIST) removed. n8n now only needs `AIPP_BASE_URL`,
  `AIPP_API_KEY`, Slack channel vars, Azure OAuth (optional), SVCMAP.
- `backend/core/config.py` — added proxy-side config: `proxy_api_key`,
  `k8s_*`, `proxmox_*`, `grafana_*`, `github_*`, `iac_*`, `ado_org_proxy`,
  `ado_project`, `ado_pat`, `gh_repo_allowlist`.

### Migration
- Add to AIPP backend `.env` on `keycloak01`:
  ```
  PROXY_API_KEY=<random-64-hex>
  K8S_API_URL=...  K8S_TOKEN=...  K8S_CA_VERIFY=false
  PROXMOX_URL=...  PROXMOX_TOKEN=...  PROXMOX_NODE=...
  GRAFANA_URL=...  GRAFANA_API_KEY=...
  GITHUB_PAT=...  GH_ORG=Subinoy2024  GH_REPO=AIPP-...
  IAC_REPO_OWNER=...  IAC_REPO_NAME=...
  GH_REPO_ALLOWLIST=owner/repo1,owner/repo2
  ADO_ORG=<slug>  ADO_PROJECT=...  ADO_PAT=...
  ```
- Shrink `.env.n8n` on the n8n host to just `AIPP_BASE_URL`,
  `AIPP_API_KEY` (same value as `PROXY_API_KEY`), Slack channels,
  Azure OAuth (optional), SVCMAP.



## [0.30.0] — 2026-02 · Iteration-30 · n8n workflows production hardening

### Fixed (correctness — Phase 1)
- **Azure static bearer removed** — every Azure workflow (#01, #04, #09,
  #10, #12, #13, #15) now starts with a shared `Azure · Get Token` node
  that exchanges `client_credentials` via
  `login.microsoftonline.com/{tenant}/oauth2/v2.0/token`. Tokens no
  longer expire mid-flow.
- **Env-var single source of truth** — dropped ghost vars
  (`AZURE_SUB`, `AZURE_TOKEN`, `RG`, `LAW_ID`, `IAC_REPO_PATH`,
  `ADO_PAT_B64`). Names now match `.env.n8n.example` 1:1.
- **IaC Drift Detector (#02)** — replaced `httpbin.org` stub with a real
  `GET /repos/{owner}/{name}/git/trees/main?recursive=1` call + LLM
  analysis over the file list.
- **Slack channels externalised** — all workflows now use
  `SLACK_CHANNEL_{DEFAULT,ALERTS,APPROVALS,DIGEST}` env vars (default
  `aipp` for single-channel workspaces).

### Added (multi-tenant + security — Phase 2)
- **Shared prelude** — every webhook flow starts with:
  Webhook → *Verify Slack Signature* (if Slack-triggered) → *Init Trace*
  → *Validate Input* → *Enforce Allowlist* (where applicable).
- **`Verify Slack Signature`** code node — HMAC-SHA256 verify against
  `X-Slack-Signature` with 5-minute replay window. No-op when
  `SLACK_SIGNING_SECRET` is unset.
- **`Validate Input`** code node — rejects on missing required fields,
  applies defaults for optional ones.
- **`Enforce Allowlist`** code node — CSV `GH_REPO_ALLOWLIST` gate on
  repo-scoped webhooks; blank list = allow all (dev).

### Added (observability + reliability — Phase 3)
- **`Init Trace`** node emits `traceId = executionId-<rand>`; every
  Slack post carries it in an italic footer for dedup + correlation.
- **HTTP + Slack + LLM nodes** get `retryOnFail=true, maxTries=3,
  waitBetweenTries=2000ms`.
- **`AIPP · 00 · Error Sink`** shared error-handler workflow — every
  other workflow attaches via `settings.errorWorkflow`. Uncaught
  failures → LLM RCA → Slack alert with severity.

### Added (tests)
- **`backend/tests/test_n8n_workflows.py`** — 15 production contracts:
  no dead env refs, no stub URLs, no static Azure bearers, retries on
  every HTTP node, error-sink attached, Slack signature verification
  on Slack-triggered flows, valid JSON, unique node names, expected
  workflow count = 16.

### Changed
- `n8n/build_workflows.py` rewritten (~700 LOC → clean generator with
  reusable node factories: `trace_init_node`, `validate_input_node`,
  `allowlist_node`, `azure_token_node`, `slack_signature_verify_node`).
- `n8n/.env.n8n.example` regenerated to reflect the single-source-of-
  truth env var set.



## [0.26.0] — 2026-02 · Iteration-26 · Dropdown fix + Batch Repo Runner

### Fixed
- **Dropdown popover** — CI/CD Platform, Cloud Platform, Deployment target
  and Auto-Deploy dropdowns appeared frozen on some browsers. Root cause was
  `backdrop-filter: blur(14px)` on `.form/.block/.gr-box/...` in
  `aipp_theme.css`. CSS spec: any ancestor with `backdrop-filter` becomes
  the containing block for `position: fixed` descendants, and Gradio 4.44's
  `DropdownOptions.svelte` positions the popover with `position: fixed` +
  viewport coords. Removed the blur from form containers and added
  explicit high-z-index overrides for `ul.options`. Restart the frontend
  container after pulling (CSS is inlined at Python startup).

### Added
- **Batch Repo Runner tab** — score-run up to 20 GitHub repos with a
  shared configuration for MS-thesis benchmarks. Results are persisted as
  `ResearchExperiment` rows and exported as CSV. Now includes a **per-repo
  BarPlot** coloured by outcome (`passed` / `failed_validation` / `error`)
  so evaluation figures come straight out of the app.
- Backend `POST /api/research/batch` — sequential per-repo generation,
  per-repo failure capture, aggregate + per-repo metrics response.
- **GitLab CI Auto-Deploy** — Integrations tab now accepts GitLab
  (gitlab.com or self-hosted). Auto-Deploy pushes the generated
  pipeline into `.gitlab-ci.yml` either as a merge request (safest) or
  a direct commit. New writer `backend/services/gitlab_writer.py`
  parallels `azdo_writer.py`.
- 20 new pytest tests (batch runner + GitLab writer via
  `httpx.MockTransport`, no new deps).

### Files
- `backend/api/research.py`
- `backend/api/integrations.py`
- `backend/services/gitlab_writer.py` (new)
- `backend/services/deployment_targets.py`
- `frontend/tabs/batch_runner.py` (new)
- `frontend/tabs/integrations.py`
- `frontend/tabs/pipeline_generator.py`
- `frontend/gradio_app.py`
- `frontend/static/aipp_theme.css`
- `backend/tests/test_iteration_26_batch_runner.py` (new)
- `backend/tests/test_iteration_26_gitlab_writer.py` (new)

---

## [0.25.0] — 2026-02 · Iteration-25 · Auto-Deploy to Onboarded Platforms

### Added
- **Integrations tab** (new) — user onboards separate deployment repositories
  (GitHub Actions or Azure DevOps). PATs stored **Fernet-encrypted** at rest.
- **Auto-Deploy panel** under Pipeline Generator — after YAML is generated the
  user chooses `Download manually` (default) or `Auto-push` via a saved
  target. Modes:
  * **Pull request** (recommended, safest) — AIPP creates a topic branch on
    the deployment repo, commits the YAML, and opens a PR back to the base
    branch chosen by the user.
  * **Direct commit** — writes straight to an existing branch. Refuses to
    auto-create branches.
- New `POST /api/integrations/targets` / `GET` / `DELETE` / `/test` +
  `POST /api/integrations/deploy` + `GET /api/integrations/deployments`
  endpoints, all authenticated.
- `deployment_targets` and `deployments` tables with a full audit trail
  (SHA-256 of YAML, commit SHA, PR URL, mode, status, error).
- New Fernet crypto helper `services/crypto_service.py` (`AIPP_FERNET_KEY`).
- Azure DevOps write adapter `services/azdo_writer.py` covering push + PR
  creation via the REST v7.1 APIs.
- GitHub adapter extended with `open_pull_request` (branch create + commit +
  PR open, idempotent).
- **12 new pytest cases** covering crypto round-trip, tamper-detection,
  Azure DevOps URL parsing, and Integrations API contract.

### Docs
- `README.md` — new Integrations tab documented, API table updated,
  license → MIT.
- New `docs/RUNBOOK.md` — production operator runbook (deploy, restart,
  backup, key rotation).
- New `CHANGELOG.md` (this file).

---

## [0.24.0] — 2026-01 · Iteration-24 · Futuristic UI + OIDC + Password Reset

- Custom `aipp_theme.css` — dark glass "control-tower" aesthetic, animated
  progress orbs (`.aipp-agent-orb`), gradient neon accents.
- OIDC login button + `/api/auth/oidc/*` flow (Google / Azure AD via
  well-known discovery URL).
- Password reset (email → signed JWT → `/api/auth/password/reset`).
  Email delivery via Resend (`RESEND_API_KEY`); dev-mode logs the link to
  stdout instead of sending.
- Brute-force protection: IP + email lockouts (`core/brute_force.py`).

## [0.23.0] — 2026-01 · Iteration-23 · JWT Auth + Policy Bundle API

- `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`.
- Seeded default admin (`AIPP_DEFAULT_ADMIN_EMAIL/PASSWORD`), auto-disabled
  once OIDC is enabled.
- `/api/policy/bundle` + `/api/policy/preview` — 12 starter Rego rules
  covering AWS, Azure, GCP compliance baselines.

## [0.22.0] · Iteration-22 · Agent-Aware MCP Guard + LLM History + OPA Preview

- `mcp/guard.py` blocks unregistered adapter calls (fail-safe `block` mode
  by default, `warn` mode via `AIPP_MCP_GUARD`).
- `llm_calls` table + `GET /api/llm/usage/history` for historical spend
  charts (thesis evaluation chapter).
- OPA policy preview accordion on the Pipeline Generator.

## [0.21.0] · Iteration-21 · Agent Registry + Deployment Target Recommender

- `agents/registry.py` + `agents/skills.py` — self-describing `AgentSkill`
  card, exposed via `/api/agents`.
- UI dropdown for specific cloud services (EKS / Lambda / AKS / Cloud Run…).
- Per-IP rate limiter (`core/rate_limit.py`), secret scanner
  (`services/secret_scanner.py`), API guardrails on `POST /api/pipelines/*`.

## [0.20.0] · Iteration-20 · Production Terraform + Native Task Usage

- 5-stage production Terraform infra pipelines (validate → plan → policy →
  approval → apply → outputs) for all 5 CIs.
- Bicep opt-in for Azure-only users; Terraform default everywhere else.
- Native task usage: `TerraformTaskV2@2` (ADO marketplace),
  `hashicorp/setup-terraform@v3` (GHA), native Harness `TerraformPlan/Apply`.

## [0.11.0 – 0.19.0] · Iterations 11 – 19 · Streaming, Doctor, Compare, Audit

- SSE streaming for agent progress + live LLM token echo.
- PipelineDoctor RCA with evidence anchoring to log lines.
- Compare Mode (static / generic-LLM / AIPP variants) with metrics
  persisted to `research_experiments`.
- Audit Log tab with colour-coded rendering + JSON export.
- LLM in-memory usage meter (`/api/llm/usage`).

## [0.1.0 – 0.10.0] · Iterations 1 – 10 · MVP

- FastAPI + Gradio scaffold.
- LangGraph state machine, 8 agents.
- 11 MCP adapters (GitHub / GitHub Actions / Azure DevOps / GitLab / Harness
  / Tekton / Kubernetes / Azure / AWS / GCP / n8n).
- PostgreSQL 15 + Alembic migrations.
- Docker Compose stack.
