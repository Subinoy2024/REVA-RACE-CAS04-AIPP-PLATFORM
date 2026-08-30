# AIPP — Defence Q&A Preparation Guide

**Standalone companion to the Capstone Final Report.**
Read this the evening before your viva. Every answer maps back to a specific chapter, code file, or empirical result in the main report so you can cite the source if pressed.

**How to use this document:**
- Sections 1-3 are the questions every examiner opens with. Rehearse these aloud until the answers feel natural, not memorised.
- Sections 4-9 are deep-dive questions organised by topic. Skim them; slow down on the ones you feel weakest on.
- Section 10 covers "trap" and lateral-thinking questions.
- Section 11 is a numbers cheat sheet — memorise the key figures.
- Section 12 is a 5-minute walk-through script for demonstrating the running system.

---

## 1. Elevator questions (memorise verbatim)

### Q1. In one sentence, what is AIPP?
> **A.** AIPP is a multi-agent LLM platform that reads any GitHub repository and generates a validated, deployment-ready CI/CD YAML for any of five platforms and three clouds, and also does evidence-anchored RCA on failing logs with RAG-backed memory of past incidents.

### Q2. In two minutes, walk me through what AIPP does.
> **A.** A user pastes a GitHub URL and picks a CI/CD platform and a cloud. Eight specialised agents run in sequence inside a LangGraph state machine — first the Repository Analysis agent reads the repo through the GitHub MCP adapter, then Technology Detection classifies the stack, then Architecture Detection identifies the deployment shape, then Planner picks the stages and approval gates, then Environment plans dev/qa/staging/prod, then a deterministic template Generator emits the YAML, then four validators check syntax + platform schema + security + environment. Every step streams live progress to a Gradio UI. Every external call goes through an MCP adapter with a runtime guard that enforces per-agent skill scopes. Once the YAML is generated, the user can push it to a separate deployment repository as a Pull Request. If the pipeline fails later, PipelineDoctor reads the log and produces a structured RCA with retrieval-augmented context from past incidents — the memory lives in pgvector inside PostgreSQL. Around the pipeline, seventeen n8n workflows handle AI-Ops — incident commander, K8s troubleshoot, SLO burn-rate, chaos experiments — and every risky workflow is gated by a Slack Block Kit human-in-the-loop card whose button clicks are HMAC-verified.

### Q3. What is the research contribution?
> **A.** Prior work has separately addressed retrieval-augmented code generation [1], multi-agent orchestration [2], tool-augmented LLMs [4][7], CI/CD failure analysis [3a][3b], and human-AI interaction [14]. To the best of my search, no publicly reported system combines all of them into a single evaluable artefact that generates production-shaped pipelines across five CI/CD platforms and three clouds, ships an evidence-anchored RCA with RAG, drives a workflow engine via a secret-vault-proxy pattern, and gates every risky action behind an HMAC-verified Slack HITL card. AIPP's contribution is the *integration* of these techniques and the *empirical evaluation* of that integration against controlled baselines.

### Q4. What is the biggest empirical result?
> **A.** On a 25-repository open-source corpus, AIPP produces a valid, executable pipeline for 89.6 % of the corpus. A static-template baseline produces 41.6 %. A generic single-shot LLM prompt produces 62.4 %. On a labelled 50-log RCA corpus, AIPP's PipelineDoctor achieves F1 = 0.898 with warm memory (49 prior incidents seeded), up from F1 = 0.83 cold. Both numbers are from live pytest runs and Chapter 10 of the report.

### Q5. What is the biggest limitation?
> **A.** Two, ranked. First, the corpus size — 25 repositories and 50 logs is enough to see the direction of the improvement but not enough to compute tight confidence intervals; a 1000-repo evaluation is future work. Second, AIPP produces the pipeline but does not run it — "did the real deployment succeed" is out of scope; that boundary was chosen deliberately because a research artefact should not hold write credentials to production infrastructure.

---

## 2. Chapter-by-chapter core questions

### Chapter 1 — Introduction

**Q6. Why is a pipeline hard to write manually?**
Every CI/CD platform has its own YAML dialect, its own task names, and its own opinion about approval gates, secret injection, cache keys, matrix builds. Add three clouds — each with its own authentication method and IaC primitives — and you have a 15-way matrix in which no cell can be safely copy-pasted into another.

**Q7. Why don't you just use ChatGPT for this?**
A generic ChatGPT prompt produces plausible-looking YAML that references packages that do not exist, tasks renamed three versions ago, or approval semantics a real change-management policy would reject. The missing ingredient is not the model — it is the surrounding scaffolding: MCP-mediated retrieval, deterministic templates, validators, and audit. The evaluation shows the generic-LLM baseline hitting 62.4 % vs AIPP's 89.6 % on the same 25 repositories.

**Q8. Where does AIPP sit in the picture?**
Between a source repository (read-only) and a target CI/CD platform (write). AIPP does not run the deployment itself — the CI/CD platform's own runners do. This boundary was chosen so a research artefact does not need to hold write credentials to production infrastructure.

### Chapter 2 — Literature Review

**Q9. What did you take from RepoCoder [1]?**
The "retrieve before generate" principle. RepoCoder applied it at code-completion scope; AIPP applies it at pipeline scope. Before any LLM call happens, the Repository Analysis agent reads the file tree, manifests, Dockerfiles, and existing pipelines, and structures them into a Pydantic object. Every downstream agent sees that object, not the raw repository.

**Q10. What did you take from AutoGen [2]?**
Multi-agent decomposition improves accuracy AND traceability compared to a monolithic prompt. AIPP applies the pattern with two conservative changes: agents exchange typed Pydantic messages (not free-text chat), and the graph is directed and linear (not fully connected).

**Q11. What did you take from Toolformer [4] and MCP [7]?**
Tool-augmented LLMs hallucinate less than parametric-memory-only LLMs. AIPP treats every external system as an MCP-style tool surface. Agents cannot import an SDK — they can only call `MCPClient.call(adapter, tool, ...)`, and the client enforces a per-agent skill scope at runtime.

**Q12. What did you take from Beller/Gousios and Gallaba et al. [3a][3b]?**
Their failure taxonomies — dependency resolution errors, flaky tests, image-pull failures, missing env vars, timeouts — are what PipelineDoctor classifies against. Their "false-positive noise" warning drove the requirement that every RCA evidence claim must quote a verbatim log line.

**Q13. Why did you cite Slack's HMAC docs [15]?**
Because AIPP verifies incoming Slack interactivity requests with the same HMAC-SHA256 scheme and 5-minute skew window Slack itself uses on the server side. Citing the docs is honest — I did not invent the scheme.

### Chapter 3 — Problem Statement

**Q14. What are the three faces of the problem?**
Correctness (dialects differ across the 15-cell matrix), drift (a green pipeline in January will fail next January because task versions are deprecated), and RCA (busy on-call engineers triage each incident from scratch even when 99 similar ones happened before).

**Q15. Who is affected?**
Platform engineering teams (they own pipelines), application engineers (they wait when pipelines break), security teams (they need the audit trail), and SREs (they own incident response).

**Q16. What is the exact research question?**
"Can a multi-agent LLM-driven system, augmented with retrieval-based memory and tool-mediated integration, generate a validated, deployment-ready CI/CD pipeline for any of five platforms and three clouds — while simultaneously producing evidence-anchored root-cause analysis for pipeline failures and coordinating a human-in-the-loop workflow suite — at higher success rates than either a static-template baseline or a naïve single-shot LLM prompt?"

### Chapter 4 — Objectives

**Q17. List your four objectives.**
1. Design and implement multi-agent orchestration for 5 CIs × 3 clouds with MCP-mediated integrations.
2. Build evidence-anchored PipelineDoctor RCA with RAG memory.
3. Integrate 17 n8n workflows via Secret-Vault Proxy + Slack Block Kit HITL.
4. Evaluate against static-template and generic-LLM baselines using 25 repositories and 50 logs.

**Q18. Where is each objective discharged?**
Objective 1 → Chapters 7 and 8.1-8.4, measured in Chapter 10 Table 10.1 (89.6 % vs 62.4 % vs 41.6 %).
Objective 2 → Chapter 8.5, measured in Chapter 10 Table 10.2 (F1 = 0.898 warm memory).
Objective 3 → Chapter 8.6, validated by `smoke_test_all.sh` and 42-second median HITL round-trip.
Objective 4 → Chapters 9 and 10 through Compare Mode + batch runner.

### Chapter 5 — Methodology

**Q19. Why 34 iterations?**
Risk containment. Big-bang integration would leave every failure open-ended. Iteration-scoped work fails loudly, rolls back cleanly, and each iteration adds one testable capability. Each iteration ended with a green pytest suite and a git commit — the whole history is in `CHANGELOG.md`.

**Q20. What was your biggest methodological change?**
Iteration-21 introduced the MCP Guard. Until then, any agent could call any adapter — a compromised agent could exfiltrate anything. I added a per-agent skill scope declaration and a runtime check. This was ~120 lines of code across `backend/agents/skills.py` and `backend/mcp/client.py` and made the governance story defensible.

**Q21. Name three specific problems you hit during development.**
1. n8n 1.6x HITL Wait-node bypass. The Wait node parameters were nested in `options` instead of at the top level. Fix: emit them at the top level and add a build-time pass that marks every upstream node with `alwaysOutputData: true` + `continueOnFail`.
2. pgvector migration on an existing Postgres volume. Switching from `postgres:15` to `pgvector/pgvector:pg15` did not auto-enable the extension. Fix: Alembic migration `34_pgvector_rag` runs `CREATE EXTENSION IF NOT EXISTS vector` first.
3. Slack signing-secret rotation. First version failed loudly when Slack re-issued the secret. Fix: read through the settings singleton so `docker compose restart backend` picks up the new value without a code change.

---

## 3. Agent + MCP + LangGraph deep dive

**Q22. Why 8 agents and not one big prompt?**
Wu et al. showed [2] that decomposition improves both accuracy and traceability. Each agent has typed I/O and can be unit-tested in isolation. If the stack is misidentified, the failure is visible at the TechnologyAgent boundary, not five minutes later when the YAML breaks.

**Q23. Why LangGraph and not a plain Python loop?**
Named nodes, explicit edges, durable step boundaries, built-in retry, visualisable graph. A hand-rolled loop works but is opaque and hard to audit.

**Q24. Why is the graph linear and not fully connected?**
Two reasons. First, reproducibility — the same input produces the same node order every time. Second, defence — a prompt-injected LLM that writes `next_agent = "commit_yaml"` into the state should not be able to reroute the graph. In AIPP, it cannot. The graph is data; the LLM never sees it.

**Q25. Explain the flow of a single generation click.**
The user submits the form. FastAPI validates and rate-limits. `PipelineService` instantiates the LangGraph state machine and calls `graph.astream(state)`. Each of the seven nodes emits SSE progress frames as it runs. The final assembled YAML passes through four validators and a secret scanner before being persisted. Total median latency: 11.4 seconds on Claude, 14.9 seconds on GPT-4.

**Q26. What does `BaseAgent` do that concrete agents do not have to?**
Provider selection, LLM SDK call, JSON stripping, Pydantic validation, and self-heal retry (max two retries with the error text fed back to the model). A concrete agent is typically 15-20 lines because all of this is inherited.

**Q27. What is an `AgentSkill` and why does it exist?**
It is a frozen dataclass declared per agent — name, label, description, skills list, input model, output model, MCP adapters used read-only, MCP adapters used with writes, and upstream dependencies. It makes agents discoverable — the UI, the docs generator, and any downstream MCP-aware system can consume the registry through `GET /api/agents`.

**Q28. How is the agent registry populated?**
At Python import time. `backend/agents/registry.py` calls `register_agent(...)` eight times — once per agent. There is no database, no config file, no runtime discovery. The registry is a module-level dict.

**Q29. Why is `AgentSkill` frozen?**
So an audit reader can trust that the skill card at inspection time is the same one that was in effect when a decision was made. If the dataclass were mutable, a runtime attacker could rewrite the scopes.

**Q30. What is the MCPClient and what does it do?**
The only object agents talk to for external systems. Three public methods: `list_tools()`, `is_configured(adapter)`, `call(adapter, tool, **kwargs)`. On every call it (a) looks the adapter up, failing fast on unknown, (b) invokes the guard, (c) redacts PAT/token/api_key kwargs before logging, (d) runs the adapter, (e) writes an audit trail row.

**Q31. What is an MCP adapter?**
A subclass of `BaseMCPAdapter` — one class per external system. Implements `list_tools()`, `is_configured()`, and `call(tool, **kwargs)`. There are eleven of them under `backend/mcp/adapters/`.

**Q32. Why in-process MCP rather than the two-process spec?**
A network hop would add ~5 ms per call × ~40 calls per generation for a single-tenant research artefact — ~200 ms of pointless latency, plus one more failure mode. The MCP *contract* is preserved (list_tools, typed calls, structured returns); only the *transport* is a Python function call. If AIPP later needs out-of-process adapters, `MCPClient.call()` is the single seam that would swap to HTTP.

**Q33. What is the MCP guard and how does it work?**
A runtime enforcement point. Uses `contextvars.ContextVar` to know which agent is currently executing (set by the `_track()` wrapper around every LangGraph node). When `MCPClient.call()` runs, it reads the context var, looks up the caller's skill card, and rejects the call if the requested adapter is not in `reads_mcp` or `writes_mcp`. Mode is `block` by default and `warn` for demos, toggled by `AIPP_MCP_GUARD`.

**Q34. What if a developer forgets to wrap a new node with `_track()`?**
`_current_agent.get()` returns `None`, the guard's caller lookup fails, and the guard raises `MCPGuardError` with `"unknown caller 'None'"`. The design fails loudly, not silently.

**Q35. What does the `_track()` wrapper actually do?**
Three things: (a) `bind_agent(name)` sets the contextvar for the duration of the node, (b) SSE `publish(agent=name, status="running")` frames stream to the UI, (c) timing + error status is captured on completion.

**Q36. What is an "MCP server" in AIPP's language?**
A `BaseMCPAdapter` subclass. The Anthropic MCP spec calls the tool side of the boundary the "server" and the LLM-app side the "client". AIPP uses those exact terms; the transport just happens to be Python function calls instead of stdio/HTTP.

**Q37. Which adapters have write tools?**
`github` (commit_file, open_pr), `github_actions` (dispatch_workflow), `azure_devops` (commit_yaml, create_pr), `gitlab` (commit_yaml, open_mr), `n8n` (activate_workflow, execute_workflow). The rest are read-only in the current release.

**Q38. Can I add a new adapter without changing the client?**
Yes. Drop a new subclass into `backend/mcp/adapters/`; `build_registry()` picks it up at boot. This is the "server discovery" pattern from the MCP spec [7] implemented at Python module scope.

---

## 4. Data + RAG deep dive

**Q39. Why PostgreSQL and not MongoDB?**
Relational integrity — pipeline runs reference repositories, RCA reports reference embeddings, audit logs reference actors. These are relationships, not documents. Postgres with SQLAlchemy 2 gives us typed schemas, Alembic migrations, and pgvector all in one process.

**Q40. Why pgvector and not Pinecone or Weaviate?**
AIPP already needs Postgres for eleven non-vector tables. Running two datastores would double operational cost, double backup complexity, and double credential surface. pgvector implements HNSW cosine similarity natively [13] with sub-100 ms latency at 10k+ vectors — verified at 210 vectors in the demonstration deployment at 47 ms p95.

**Q41. Why did you pick 1536-dim embeddings?**
That is the output size of OpenAI's `text-embedding-3-small`, the default embedder. It is a good size for HNSW indexing (fits in cache for tens of thousands of vectors) and gives sufficient semantic resolution for our RCA use case. A future evaluation would compare against `text-embedding-3-large` (3072-dim) at higher cost.

**Q42. Why RAG instead of fine-tuning?**
Fine-tuning bakes customer incident data into model weights — privacy problem, expensive to update, hard to audit. RAG keeps every RCA in a queryable table the customer can inspect / redact / delete row by row. Retrieval improves RCA F1 from 0.83 cold to 0.94 warm on our 50-log corpus.

**Q43. What is the retrieval query for a fresh RCA?**
`incident_context + first 400 words of log`, truncated at 4000 characters. This mix captures both the "what was happening" narrative and the concrete log lines. Testing different queries (context-only vs log-only vs mixed) showed the mixed query performs best.

**Q44. Why "prior evidence, do NOT cite"?**
Without the guard, an LLM asked "what caused this OOM?" that has just been shown three past OOMs will happily copy evidence lines from the past into the current report. This produces plausible but false attribution. The explicit instruction blocks that failure mode.

**Q45. What is the HNSW index and why?**
Hierarchical Navigable Small World graphs — Malkov and Yashunin's ANN algorithm [13]. It gives sub-linear search complexity for high-dimensional vectors with strong recall. pgvector supports it as a first-class index type; `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`.

**Q46. What happens if the retrieval step fails?**
Best-effort. If pgvector is missing, the embedder crashes, or the DB is offline, `find_similar()` returns an empty list. The fresh RCA still runs unchanged — retrieval is enrichment, not a critical path. Verified by `test_rca_embedding.py::test_find_similar_pgvector_missing`.

**Q47. What is the confidence score for and how is it computed?**
It is a self-reported number from the RCA agent (0-1) indicating how sure the model is about the identified root cause. It is capped at 0.5 for logs shorter than 50 useful lines because short logs contain insufficient evidence. Above 0.6, the precision on the labelled corpus is monotonically ≥ 0.9 — this gives operators a defensible threshold for routing (auto vs manual triage).

---

## 5. Security + HITL deep dive

**Q48. What stops a malicious workspace from replaying a Slack click?**
Three things: (a) Slack signs every request with a per-workspace signing secret we validate with HMAC-SHA256, (b) requests with a timestamp older than 5 minutes are rejected, (c) the resume URL contains an n8n one-shot signed token that becomes invalid the instant the workflow resumes.

**Q49. What is HMAC-SHA256 and how does Slack use it?**
Hash-based Message Authentication Code — the sender signs the message with a shared secret; the receiver re-computes the signature with the same secret and compares. Slack's version [15] concatenates version + timestamp + body, HMACs with the workspace signing secret, and puts the result in the `X-Slack-Signature` header. AIPP replicates the exact scheme.

**Q50. Why a 5-minute skew window?**
Slack itself enforces the same window on its own side. Requests older than 5 minutes are rejected as replay attempts. Legitimate clicks always arrive within seconds — the window is loose enough to tolerate clock drift on the AIPP host but tight enough to prevent replay days later.

**Q51. What is the "webhook-waiting" guard?**
Defence in depth. After HMAC passes, the code additionally checks that the button's `value` (the resume URL) contains the substring `webhook-waiting`. Even if the signing secret leaks, an attacker who could construct valid signed requests cannot point the resume call at an arbitrary URL — the guard pins the URL shape to what n8n emits.

**Q52. What is the Secret-Vault Proxy pattern?**
n8n workflows hold zero infrastructure credentials. Every external call (Kubernetes, GitHub, Grafana, Proxmox, ADO) goes to `POST /api/proxy/*` on the AIPP host with a shared `PROXY_API_KEY` bearer. AIPP fans out with the *real* credentials. A compromised n8n container cannot bypass allowlists or exfiltrate keys.

**Q53. Why not just use HashiCorp Vault?**
It is on the Chapter 11 future-work list. The current release keeps secrets in `backend/.env` for reproducibility — a Vault dependency would add operational friction for a research artefact. When AIPP goes to production, Vault or Azure Key Vault is the natural next step and the migration point is the settings singleton.

**Q54. Why Fernet encryption for PATs and not plain database column encryption?**
Fernet is authenticated encryption (AES-128-CBC + HMAC-SHA256) — it detects tampering as well as preventing reads. Postgres column encryption via `pgcrypto` would work but requires the DB to hold the key; Fernet lets the key stay outside the DB in `AIPP_FERNET_KEY`. A stolen Postgres dump alone cannot recover the PATs.

**Q55. Why Pull-Request mode by default?**
GitOps orthodoxy [8]. Every change should flow through a reviewed PR. A research artefact that silently commits YAML would fail security review at any real organisation. PR-by-default keeps a human in the merge decision.

**Q56. What is the secret scanner and when does it run?**
Before every auto-deploy commit. Regex-based scanner looking for `AWS_ACCESS_KEY_ID`, `AKIA`, `ghp_`, `xoxb-`, `-----BEGIN RSA PRIVATE KEY-----`, etc. A match refuses the commit with an audit row. This is `backend/services/secret_scan.py`.

**Q57. What is the environment validator refusing?**
Any generated YAML that deploys to Production without a manual approval gate. Any Terraform apply that skips the plan stage. These are hard refusals — not opinions of the LLM — that fire after the LLM output has been assembled.

---

## 6. n8n + workflows deep dive

**Q58. Are the 17 workflows really Community-Edition compatible?**
Yes. `test_n8n_workflows.py` enforces at build time: no Code nodes, no `$vars` references (Variables API is Enterprise-only), no dependencies on Enterprise-only node types. The 17 JSONs import cleanly into stock `n8nio/n8n:latest`.

**Q59. Why n8n and not Temporal or Argo Workflows?**
Three reasons. First, target-audience familiarity — n8n's UI is approachable for SRE / platform teams who are not full-stack engineers. Second, Community Edition is free and fully sufficient. Third, every workflow is a declarative JSON artefact that an examiner can inspect visually. Temporal would give better durability semantics but at the cost of learning curve and infrastructure overhead — the wrong trade-off for a capstone.

**Q60. Give me an example of a workflow that uses the Secret-Vault Proxy.**
Workflow 07 (K8s Troubleshoot Assistant). A webhook arrives with a pod name + namespace. The workflow calls `POST /api/proxy/k8s/pods/{ns}/{name}` on AIPP with the `PROXY_API_KEY` bearer. AIPP uses its Kubernetes token — held only in AIPP's env — to describe the pod, fetch events, and return the structured result. The workflow then feeds this into an OpenAI LLM node to generate a troubleshooting summary and posts to `#platform-troubleshoot` on Slack.

**Q61. What happens if AIPP is unreachable from n8n?**
The workflow fails at the proxy call. The HITL flows (01, 03, 04, 14, 16) are pre-hardened — every upstream node of a Wait node is marked `alwaysOutputData: true` + `continueOnFail`, so the flow still reaches the Wait node and parks. Non-HITL flows fail loud, and the error sink workflow (00) captures the failure with a Slack alert.

**Q62. How do you deploy the 17 workflows?**
`python3 n8n/build_workflows.py` regenerates all JSONs. `bash n8n/scripts/deploy.sh --activate-all` pushes to the n8n REST API idempotently (PUT if exists, POST if new) and flips every one to active. Verified by `smoke_test_all.sh`.

---

## 7. Testing + evaluation deep dive

**Q63. How many tests do you have?**
500+ pytest cases across 48 files, running in ~15 seconds under two xdist workers. Full breakdown in Chapter 9 Table 9.2.

**Q64. Explain the 25-repository evaluation corpus.**
Twenty-five open-source repositories curated in `tests/research/repos.corpus.csv`. Mix of languages (Python, Node.js, JVM, Go, static sites) and shapes (monolith, microservice, K8s, VM, Lambda, static). For each repo, we run three variants — static template, generic-LLM prompt, AIPP full — through the Compare Mode tab and check whether the generated YAML passes AIPP's four validators.

**Q65. Why 25 and not 100?**
Manual review overhead. Every one of the 75 outputs (25 × 3 variants) was inspected by hand to verify the validator's verdict against ground truth. Scaling to 100 or 1000 requires automating the ground-truth check, which is Chapter 11 future work.

**Q66. Explain the 50-log RCA corpus.**
Ten labelled failures of each of five classes: `ImagePullBackOff`, `OOMKilled`, dependency-resolution, flaky-test, missing-env-var. Sourced from public GitHub Actions run outputs and reproduced synthetically. For each log we run PipelineDoctor with a cold `rca_embeddings` table and a warm one (49 prior RCAs seeded).

**Q67. What is the difference between cold and warm memory?**
Cold — the `rca_embeddings` table is empty, so the retrieval step returns nothing and the LLM sees only the current log. Warm — 49 prior labelled RCAs are seeded first, so retrieval returns the top-3 cosine-close past incidents and prepends them as prior evidence.

**Q68. Why does warm memory help?**
Because RCA failure classes recur. The hundredth OOMKilled report benefits from the previous ninety-nine. Retrieval gives the LLM a strong prior that this class of failure exists and what the corrective action typically is. F1 improves from 0.83 to 0.94.

**Q69. Which failure class is hardest to classify?**
Flaky tests (F1 = 0.78). They look similar to real test failures at the log level; the classifier needs additional signal like "same test passes on retry" which is not always in the log we are analysing.

**Q70. What is the latency of the RCA?**
Median 6.2 s end-to-end including the retrieval step. pgvector retrieval p95 is 47 ms at 210 stored RCAs — the LLM call dominates.

---

## 8. Technology-choice questions

**Q71. Why FastAPI and not Flask or Django?**
Native async support (needed for LLM calls + SSE streaming), first-class OpenAPI schema generation, tight Pydantic integration for request/response validation. Flask needs plugins for all three; Django is heavier than we need.

**Q72. Why Gradio and not React?**
Target audience for the demo is a research committee, not a customer base. Gradio ships a serviceable UI on top of a Python backend with no separate build pipeline. If AIPP moves to product, React is the natural next step.

**Q73. Why Docker Compose and not Kubernetes?**
A reviewer should be able to boot the stack in under 15 minutes on a laptop. Kubernetes would add operational friction with zero research benefit. When AIPP goes to production, Kubernetes is the natural next step — the Compose file translates to a Helm chart.

**Q74. Why the Emergent Universal LLM Key?**
It abstracts the provider selection — the same code path works with Claude, GPT-4, or Gemini via one environment variable. Lets us swap providers in Chapter 10 to check model-dependence without touching agent code.

**Q75. Why Python and not TypeScript / Go?**
LLM SDK maturity in Python (Anthropic, OpenAI, and Gemini all publish first-class Python SDKs). LangGraph and pgvector are Python-first. The MCP spec has Python and TS clients, but the ecosystem is heavier on Python.

**Q76. Why did you build this on a Proxmox VM and not on cloud?**
Cost, reproducibility, and vendor-neutrality. A local VM lets me run experiments without cloud bill anxiety, redeploy from a known-good snapshot in seconds, and keeps the evaluation cloud-agnostic (AIPP claims to be multi-cloud; running the evaluation on one cloud would undermine that claim).

---

## 9. Future-work questions

**Q77. What would you build if you had another six months?**
Three things. First, Slack Attribution — persist the Slack user_id back into the resumed n8n execution so downstream Slack posts `@`-mention the human who signed off. Second, Compliance PDF Export on the Approvals tab — a one-click ISO 27001 evidence-pack. Third, extend the evaluation from 25 to 1000 repositories by scripting the ground-truth check.

**Q78. What about AutoRCA-triggered PR generation?**
On the Chapter 11 list. When PipelineDoctor identifies a specific failure class with confidence ≥ 0.8, autogenerate a corrective Pull Request against the source repository — bumping a resource limit, adding a missing env var, pinning a flaky test — instead of just reporting the RCA. This is the "generate a fix, not a report" direction.

**Q79. Could AIPP become a SaaS product?**
Yes. The natural product shape is a SaaS where a team plugs in their GitHub org, AIPP maintains their pipeline files across all repos, and the 17 n8n workflows run as a managed multi-tenant service. For the capstone, we stop at the research contribution.

**Q80. How would you handle cross-organisation memory sharing?**
Chapter 11 future-work item 7. Anonymised sharing of `rca_embeddings` across organisations so a first-incident-in-org-A can benefit from a hundred-incident history in org-B. Needs a privacy-preserving embedding-only exchange protocol — the raw log content never leaves the source org. Non-trivial; explicitly flagged as long-horizon.

---

## 10. Trap / lateral-thinking questions

**Q81. If the LLM is that important, isn't AIPP just an LLM wrapper?**
No. The LLM is the *decision-making* substrate but not the *architecture*. Remove the LLM and AIPP still has: an MCP-mediated tool layer, a LangGraph state machine, a deterministic template generator, four validators, a secret scanner, a Fernet-encrypted PAT store, a Secret-Vault Proxy, an HMAC-verified Slack bridge, an audit-log-driven UI, 500+ tests, and 17 n8n workflows. The research contribution is the *scaffolding* around the LLM.

**Q82. What if the LLM hallucinates a real-looking pipeline that is subtly wrong?**
That is what the four validators exist to catch. Syntax, platform schema, security, environment. On the 25-repo corpus, the two cases where the LLM produced something plausible-but-wrong were caught by the environment validator — one was a Production deploy without approval, one was a Terraform apply without plan. Both were correctly refused.

**Q83. What is your risk if the LLM provider goes down?**
Two mitigations. First, the universal LLM key abstracts three providers — Claude, GPT-4, Gemini — so a single-provider outage does not stop the platform. Second, PipelineDoctor RCA (which is the most user-facing feature) gracefully degrades to a template-based report if the LLM is unreachable; retrieval-only context is still returned.

**Q84. What if someone submits a malicious repository URL?**
Two guards. First, the Repository Analysis agent reads through the GitHub MCP adapter, which uses the user's own PAT and cannot escalate. Second, the LLM prompt-injection surface is bounded — the Repository Analysis agent does not call the LLM; only the downstream agents do, and by then the repository content has been structured into a typed Pydantic object.

**Q85. What is your worst failure mode?**
An LLM that produces perfectly valid YAML which passes all four validators but is subtly wrong in a way only a human reviewer would catch — for example, referencing a Docker image tag that will be pulled at deploy time but silently rolls to a newer version next month. This is the "pipeline drift" problem [3b] and it is why the auto-deploy path defaults to Pull Request mode with a human reviewer.

**Q86. If I told you your Slack HMAC verification was broken, how would you verify?**
Run `pytest backend/tests/test_slack_interactions.py -q`. The test suite covers the happy path, tampered signature, stale timestamp, missing secret, bogus action_id, malicious value, and non-action ack. All 13 cases must pass. If any fails, the bridge is broken.

**Q87. Have you tested against a real n8n instance or just the mock?**
Real. The demonstration deployment on `keycloak01` runs against a production `n8nio/n8n` container. Verified with `hitl_demo.sh` — a synthetic webhook fires, the workflow parks, a Slack button click posts to `/api/slack/interactions`, the parked execution resumes, the audit row lands in `audit_logs` within 3 seconds. All 10 HITL round-trips during the evaluation completed successfully.

**Q88. Where would AIPP fail on a public cloud production deployment?**
Two immediate gaps. First, `backend/.env` holds credentials in plaintext — production should have Vault or Azure Key Vault (Chapter 11 future work). Second, the demonstration is single-tenant — multi-tenant would need per-tenant DB isolation, per-tenant rate limits, per-tenant PROXY_API_KEY rotation. Both are known and named in the report.

---

## 11. Numbers cheat sheet (memorise before viva)

| Metric | Value |
|---|---|
| CI/CD platforms supported | **5** (ADO, GHA, GitLab, Harness, Tekton) |
| Clouds supported | **3** (AWS, Azure, GCP) |
| Agents | **8** |
| MCP adapters | **11** |
| n8n workflows | **17** |
| Gradio tabs | **13** |
| FastAPI routers | **15** |
| PostgreSQL tables | **13** |
| pytests | **500+** across 48 files |
| Development iterations | **34** |
| Bibliography refs | **20** IEEE-style |
| Screenshots + diagrams | **18** |
| Design decisions (§7.10) | **20** with Why/What/How |
| — | — |
| Pipeline gen success — AIPP | **89.6%** |
| Pipeline gen success — generic LLM | 62.4% |
| Pipeline gen success — static template | 41.6% |
| — | — |
| RCA precision (warm) | 0.917 |
| RCA recall (warm) | 0.880 |
| RCA F1 (warm) | **0.898** |
| RCA F1 (cold) | 0.83 |
| — | — |
| Pipeline gen median latency | 11.4 s (Claude) |
| RCA median latency | 6.2 s |
| pgvector p95 retrieval | 47 ms |
| HITL round-trip median | 42 s |
| HMAC skew window | 5 min |
| — | — |
| Report length | ~70 pages · 21,201 words |
| Repository open-source licence | MIT |

---

## 12. Live-demo walk-through script (5 minutes)

If the examiner asks for a live demonstration, run this exact sequence on the VM:

1. **Open the Gradio UI** at `http://<vm-ip>:3300`. Log in as admin. Show the 13 tabs.
2. **Pipeline Generator tab** — paste `https://github.com/pallets/flask`, pick `github_actions` + `aws`, click Generate. Point at the agent orbs lighting up. When done, show the generated YAML.
3. **PipelineDoctor tab** — upload a real failing log (any file under `tests/research/rca_corpus/`). Show the structured RCA report: root cause box, evidence lines with verbatim quotes, retrieved_from_memory section.
4. **HITL Approvals tab** — show past HITL decisions with 🟢/🔴 markers. Click Download JSON for the ISO 27001 evidence-pack.
5. **n8n Workflow Status tab** — show all 17 workflows active. Point at the 4 HITL flows in "running" state (parked at Wait).
6. **Terminal side-window** — `bash n8n/scripts/hitl_demo.sh`. Watch the workflow park in n8n UI, watch the Slack card appear in `#platform-approvals`. Click ✅ Approve. Watch the card seal to "✅ Approved by @you". Return to Gradio HITL Approvals tab — refresh. New row appears within 3 seconds.
7. **Compare Mode tab** — show the static-vs-generic-vs-AIPP bar chart. AIPP is the tallest bar.
8. **Wrap up** — "the whole flow you just saw is driven by eight agents in a LangGraph state machine, gated by an MCP client with runtime skill scopes, audited to PostgreSQL, and packaged in three Docker containers."

---

## Closing note

Answer honestly. If you don't know something, say "I don't know — that's not in the scope I evaluated" rather than guess. Every claim in this document maps to a specific chapter, code file, or test case in the main report — if an examiner presses you, point to the source. The examiners' role is to test whether you understand *your own* work, not to trip you up on trivia.

Good luck.

_— End of Defence Q&A Preparation Guide —_
