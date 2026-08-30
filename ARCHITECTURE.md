# AIPP · System Architecture

<!-- ==================================================================== -->
<!-- FOR AI / LLM READERS — DO NOT REMOVE                                  -->
<!-- ==================================================================== -->
> **AI-readable preamble.** This document is structured so an LLM can
> parse it without prose walls. Every fact worth citing sits in a table,
> a bullet, or a code-block. Section IDs are stable — link to
> `#3-sequence-...` etc.
>
> **Product one-liner.** AIPP takes a GitHub URL, runs 8 specialised
> agents through a LangGraph state machine, and produces a
> deployment-ready CI/CD YAML for the user-chosen platform + cloud +
> deployment target. Every external I/O flows through the MCP layer
> (11 adapters). All state is persisted in PostgreSQL with an
> append-only `audit_logs` table.
>
> **Sibling docs** (linked, don't duplicate here):
> - `docs/AGENT_REGISTRY.md` — agent skill contracts + why not A2A
> - `docs/MCP_ARCHITECTURE.md` — why MCP + the 11 adapters
> - `docs/PRODUCTION_HARDENING.md` — known gaps outside thesis scope
> - `docs/PROPOSAL.md` — full academic proposal
<!-- ==================================================================== -->

---

## 1 · Layered view

```
┌────────────────────── Presentation ───────────────────────────┐
│  Gradio Blocks (frontend/gradio_app.py) — 13 tabs             │
│  Generator · Integrations · Doctor · n8n · Approvals ·        │
│  Compare · Audit · Agents · Agent Trace · Batch Runner ·      │
│  Enterprise SSO · LLM History                                  │
└──────────────────────────┬────────────────────────────────────┘
                           │ HTTP (JSON / multipart / SSE)
┌──────────────────────────▼────────────────────────────────────┐
│  API layer (backend/api/*.py) — 15 FastAPI routers             │
│  repositories · pipelines · pipeline_doctor · workflows        │
│  research · deployment · integrations · llm · auth · policy    │
│  identity_providers · agent_traces · proxy · webhooks · slack  │
└─────────────┬──────────────────────┬──────────────────────────┘
              │                      │
              ▼                      ▼
┌───────────────────────┐  ┌────────────────────────────────────┐
│  Services             │  │ Orchestrator (LangGraph)           │
│  pipeline / audit     │  │ StateGraph(AIPPState)              │
│  n8n / llm_usage      │  │ 7 nodes for generation             │
│  secret_scanner       │  │ 1 separate node for RCA            │
└─────────┬─────────────┘  └────────────┬───────────────────────┘
          │                             │
          │                             ▼
          │              ┌──────────────────────────────────────┐
          │              │ Agents (backend/agents/*)            │
          │              │ 8 agents, each declared in registry  │
          │              │ Repository · Technology · Architecture│
          │              │ Planner · Environment · Generator    │
          │              │ Validator · PipelineDoctor (RCA)     │
          │              └────────────┬─────────────────────────┘
          │                           │
          │                           ▼
          │              ┌──────────────────────────────────────┐
          │              │ MCP Client (backend/mcp/*)           │
          │              │ 11 adapters — the ONLY doorway to    │
          │              │ external systems.                    │
          │              │ github · gitlab · azure_devops       │
          │              │ github_actions · gitlab_ci · harness │
          │              │ tekton · kubernetes · aws · azure    │
          │              │ gcp · n8n                            │
          │              └──────────────────────────────────────┘
          │
          ▼
┌───────────────────────────────────────────────────────────────┐
│  Data layer (backend/database/*)                              │
│  PostgreSQL 15 + pgvector — core tables:                      │
│  repositories · pipeline_runs · rca_reports                   │
│  audit_logs · research_experiments · users                    │
│  integrations · identity_providers · agent_traces             │
│  RAG memory: pipeline_embeddings · rca_embeddings             │
│  (1536-dim vectors, HNSW cosine indices)                      │
└───────────────────────────────────────────────────────────────┘
```

---

## 2 · Component responsibilities

| Layer | Package | Contains | Not responsible for |
|-------|---------|----------|---------------------|
| Presentation | `frontend/` | Gradio 4.44 UI, 13 tabs, SSE consumer | Business logic |
| API | `backend/api/` | 15 route handlers, request validation, rate limit | LLM prompts, DB rows |
| Services | `backend/services/` | Orchestration wrappers, secret scanning, audit, RCA embedding, ADO / GitLab writers | Route wiring |
| Orchestrator | `backend/orchestrator/` | LangGraph state machine, progress SSE bus | LLM calls |
| Agents | `backend/agents/` | 8 specialised LLM prompts + Pydantic I/O | Network calls |
| MCP | `backend/mcp/` | Tool registry, 11 adapters | Business decisions |
| Generators | `backend/generators/` | 5 platform-specific YAML templates | LLM output |
| Validators | `backend/validators/` | 4 deterministic YAML checks | Auto-fix |
| Data | `backend/database/` | SQLAlchemy models, async connection, pgvector RAG | Cross-request state |
| n8n bridge | `n8n/build_workflows.py` | Generates 20 workflows (webhook / form / schedule / error triggers, Slack Block Kit HITL) | n8n runtime |

---

## 3 · Sequence — Pipeline Generation (SSE)

```
User ─┐
      │  POST /api/pipelines/generate/stream
      ▼
FastAPI:pipelines.py ──► RateLimiter.check(ip) ──► ok
      │
      ▼
PipelineService.generate()
      │
      ▼
LangGraph  ─── stream_id ──►  progress SSE bus
      │
      │  ┌─────────────── For each of 7 nodes ───────────────┐
      ├──►│  publish(agent="repository_analysis", running) │
      │   │  RepositoryAgent.run(req)                       │
      │   │    └── MCPClient.call("github", "list_files")   │
      │   │  publish(status="done")                         │
      │   └────────────────────────────────────────────────┘
      │
      ▼
Final AIPPState with generated YAML
      │
      ▼
secret_scanner.scan(yaml)         # annotate result.security_scan
      │
      ▼
Persist PipelineRun row in Postgres
      │
      ▼
audit_logs: "pipeline.generate.done"
      │
      ▼
SSE frame: {"kind":"result", "payload":{...}}   ──► Frontend renders
```

**Failure paths:**
- MCP error → LangGraph node raises → SSE frame `{"kind":"error"}`
- Validator fails → self-healing retry (max 2) → if still fails,
  `status=completed_with_warnings`, but result still returned
- Rate limit → HTTP 429 with `Retry-After` header

---

## 4 · Sequence — Root Cause Analysis (Pipeline Doctor)

```
User uploads CI log ─┐
                     │  POST /api/pipeline-doctor/analyze  (multipart)
                     ▼
FastAPI:pipeline_doctor.py ──► RateLimiter.check(ip) ──► ok
                     │
                     ▼
validate_upload(size, ext)   ──► ok
                     │
                     ▼
sha256(log_text)             # audit fingerprint, not the content
                     │
                     ▼
run_rca(ci_platform, log_text, incident_context)
                     │
                     ▼
PipelineDoctorAgent
      │
      ├── Number every log line (L0001-L1500)
      ├── sanitize_repository_snippet(text)        # prompt-injection filter
      ├── BaseAgent._chat_json(prompt)             # calls LLM (Claude/GPT)
      │       └── Validate against RCAReport schema
      │       └── On validation error → retry (max 2) with error feedback
      │
      ▼
RCAReport {failed_stage, root_cause, confidence,
           evidence:[{line_range, snippet, interpretation}],
           ai_inferences, corrective_actions, preventive_actions}
      │
      ▼
Persist to Postgres rca_reports
      │
      ▼
audit_logs: "pipeline_doctor.analyze.done"
      │
      ▼
Return JSON to UI
```

**Guarantees:**
- Every `evidence` item cites a verbatim log range → no fabricated errors.
- `confidence ≤ 0.5` when the log has fewer than ~50 useful lines.
- `ai_inferences` is a **separate** list from `evidence` — reviewers can
  distinguish log-grounded facts from model interpretation.

---

## 5 · Sequence — Commit YAML to repo

```
User picks target_branch ──┐
                           │  POST /api/deployment/commit
                           ▼
FastAPI:deployment.py
                           │
                           ├── target_branch mandatory     (no fallback)
                           ├── ci_platform ∈ known set     (5 platforms)
                           │
                           ▼
secret_scanner.scan_report(yaml)
                           │
                           ├── blocked? ──► HTTP 400
                           │                {"error":"secret_detected", findings:[...]}
                           │
                           ▼
GitHubAdapter.commit_file(url, pat, branch, path, content)
                           │
                           ▼
PyGithub → PUT /repos/{owner}/{repo}/contents/{path}
                           │
                           ▼
audit_logs: "deployment.commit"  { branch, path, sha }
                           │
                           ▼
Return {"ok":true, commit_sha, commit_url}
```

**Safety contract (never violated):**
- No `main` fallback. No auto-create branch. No auto-create file at any
  path other than the CI-platform-specific one.
- Every commit is audited.
- Every commit runs the secret scanner first.

---

## 6 · Data model

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `repositories` | Optional cache of analysed repos | id, owner, name, branch |
| `pipeline_runs` | One row per Generate click | id, repo_url, ci, cloud, yaml, plan_json, validation_json, seconds, status |
| `pipeline_embeddings` | pgvector — 1536-dim vector per successful run | id, run_id, content, embedding |
| `rca_reports` | One row per Doctor upload | id, ci_platform, root_cause, confidence, log_sha256, evidence_json |
| `rca_embeddings` | pgvector — RAG memory for PipelineDoctor | id, rca_id, content, embedding |
| `audit_logs` | Append-only decision trail (agents, deployments, HITL clicks) | id, action, actor, tool, details_json, created_at |
| `research_experiments` | Batch benchmark metrics | id, run_id, variant, metrics_json |
| `users` | Auth (default admin + OIDC-provisioned) | id, email, password_hash, role, is_default |
| `integrations` | Fernet-encrypted PATs for ADO / GitLab / GitHub write | id, platform, credentials_enc |
| `identity_providers` | OIDC config (Keycloak / Azure AD / Google) | id, kind, discovery_url, client_id |
| `agent_traces` | LangGraph per-node execution trace | id, run_id, node, input_json, output_json, seconds |

**Retention:** all rows kept indefinitely in dev. Production hardening
task (`PRODUCTION_HARDENING.md § 5.4`): 90-day partitioning on `audit_logs`.

---

## 7 · State machine (LangGraph) — node order

```
 START
   │
   ▼
 [repository_analysis]      (MCP: github.list_files, get_file_content)
   │
   ▼
 [technology_detection]     (LLM refinement over heuristics)
   │
   ▼
 [architecture_detection]   (LLM classifies deployment shape)
   │
   ▼
 [pipeline_planning]        (LLM picks stages; obeys pipeline_type + deployment_target)
   │
   ▼
 [environment_deployment]   (LLM sets triggers + approval per env)
   │
   ▼
 [pipeline_generation]      (deterministic template rendering, no LLM)
   │
   ▼
 [pipeline_validation]      (4 validators; self-heal retry up to 2×)
   │
   ▼
  END
```

**8th agent** (`pipeline_doctor_rca`) is not in this graph — it's a
separate one-shot invocation triggered by the Doctor tab.

---

## 8 · Configuration surface

`.env` (all optional except LLM key + Postgres):

| Group | Vars | Effect if missing |
|-------|------|------------------|
| Postgres | `POSTGRES_URL`, `POSTGRES_SYNC_URL` | App fails to start |
| LLM key | `EMERGENT_LLM_KEY` (or vendor keys) | App fails LLM calls |
| n8n | `N8N_BASE_URL`, `N8N_API_KEY` | n8n tab shows *not configured* |
| CI creds | `AZURE_DEVOPS_PAT`, `GITLAB_TOKEN`, `HARNESS_API_KEY`, ... | Adapter registers, returns *not configured* |
| Cloud creds | `AZURE_*`, `AWS_*`, `GCP_*`, `KUBECONFIG` | Same as CI creds |
| Runtime | `MAX_LOG_UPLOAD_BYTES`, `LOG_LEVEL`, `AIPP_INTERNAL_BACKEND_URL` | Safe defaults |

---

## 9 · Failure isolation

| Failure | Blast radius | Recovery |
|---------|--------------|----------|
| One adapter down (e.g. n8n unreachable) | That tab shows error; rest unaffected | Adapter retries on next call |
| LLM API down | Generate/Doctor endpoints return HTTP 502 | User sees clear "LLM error" |
| Postgres down | Startup fails loudly | Restart with reachable DB |
| One agent raises | LangGraph stops; SSE sends error frame | UI shows failing agent, prior results preserved |
| Validator fails | Self-heal retry; if still fails, `completed_with_warnings` | UI surfaces the check names |

---

## 10 · Extension points

If you want to extend AIPP, these are the four supported extension seams:

1. **Add a new CI platform** — `backend/generators/<name>.py` + entry in
   `deployment.CI_PATH` + adapter for post-commit triggering.
2. **Add a new agent** — see `docs/AGENT_REGISTRY.md § 5`.
3. **Add a new MCP adapter** — subclass `BaseAdapter`, call
   `_register_tools()`. See `docs/MCP_ARCHITECTURE.md § 3`.
4. **Add a new deployment target** — add to
   `models/pipeline.DeploymentTarget` enum + `CLOUD_TARGETS` matrix.

Every seam has an existing example to copy from.

---

## 11 · n8n + Slack HITL Bridge (Iteration 31-34)

AIPP ships **17 n8n workflows** for SRE / Platform Engineering that all
follow the same Secret-Vault-Proxy contract: n8n holds zero infra secrets;
every external call lands on `/api/proxy/*` on the AIPP host, which fans
out with AIPP-side credentials.

### 11.1 · The 17 workflows

| # | Workflow | Trigger | Slack channel |
|---|----------|---------|---------------|
| 00 | Error Sink | errorTrigger | `#platform-alerts` |
| 01 | Azure Subscription Vending | webhook | `#platform-approvals` |
| 02 | IaC Drift Detector | schedule (03:00 daily) | `#platform-drift` |
| 03 | Access Review Automator | schedule (quarterly) | `#security-access-review` |
| 04 | Developer Self-Service Portal | form | `#platform-provisioning` |
| 05 | Pipeline Status Digest | schedule (30 min) | `#platform-status` |
| 06 | K8s Health Scorecard | schedule (07:00 daily) | `#platform-k8s` |
| 07 | K8s Troubleshoot Assistant | webhook | `#platform-troubleshoot` |
| 08 | Grafana Observability Auto-Remediator | webhook | `#platform-alerts` |
| 09 | Weekly Azure Cost Review | schedule (Mon 09:00) | `#finops` |
| 10 | Incident Commander Bot | webhook (Azure Monitor) | `#incidents` |
| 11 | SOP / Runbook Generator | webhook | `#sre-runbooks` |
| 12 | Azure SLO Burn-Rate Monitor | schedule (5 min) | `#sre-slo` |
| 13 | DR Readiness Drill Scheduler | schedule (quarterly) | `#sre-dr` |
| 14 | Chaos Engineering Assistant | form | `#sre-chaos` |
| 15 | Log Anomaly Hunter | schedule (hourly) | `#sre-logs` |
| 16 | Pipeline Review Gate (HITL) | webhook | `#platform-approvals` |

### 11.2 · HITL bridge sequence

```
n8n workflow (e.g. Chaos, Pipeline Review)
      │
      ▼
[Slack · Post Block Kit card]     ← ✅ Approve / ❌ Reject buttons
      │                              value = n8n resume URL
      ▼
[Wait node — resume: webhook]     ← parked with waitTill=null
      │
      │   Slack user clicks button
      ▼
Slack → POST /api/slack/interactions   (AIPP host)
      │
      ├─ HMAC-SHA256 verify (X-Slack-Signature, 5-min skew)
      ├─ decode payload — extract action_id ∈ {approve, reject} + resume URL
      ├─ guard: resume URL must contain "webhook-waiting"
      ▼
GET  {resumeUrl}?a=approve|reject     (browser-shaped UA)
      │
      ▼
n8n resumes the parked execution   ── branches on IF node ──▶ downstream
      │
      ▼
AIPP audit_logs INSERT
   { action="slack.hitl.decision", actor=<slack_user>,
     details={decision, slack_user_id, slack_channel,
              n8n_execution_id, workflow_hint, n8n_resume_status} }
      │
      ▼
Return Block Kit `response_action: update`
    → Slack replaces card with "✅ Approved by @user · sealed"
```

### 11.3 · PipelineDoctor RAG memory

```
POST /api/pipeline-doctor/analyze
      │
      ├─ retrieval_query = incident_context + first 400 words of log
      ├─ EmbeddingService.embed(query) → 1536-dim vector
      ├─ SELECT ... FROM rca_embeddings ORDER BY embedding <=> :q LIMIT 3
      │       (pgvector cosine ANN, HNSW index)
      ├─ format_context_block(similar) prepended to LLM prompt
      │
      ▼
run_rca(ci_platform, log_text, augmented_context)
      │
      ▼
Persist RCAReport
      │
      ▼
embed_and_persist(rca_id, report_json)   ← fire-and-forget hook
      │
      ▼
Response includes retrieved_from_memory[] for trust-but-verify
```

Best-effort: pgvector missing / embedder crash / DB offline never blocks
a fresh RCA — the retrieval step just returns `[]` and the analyse call
runs unchanged.
