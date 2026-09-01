# AGENTS.md · Developer & AI Assistant Guidelines

This document provides context, architectural boundaries, verified milestones, runtime preferences, and current progress state for AI assistants (like Antigravity / Gemini) and human developers working on **AIPP (Automated Pipeline Platform)**.

---

## 0. Current System State & Verified Milestones

- ✅ **Local Kubernetes Cluster**: Deployed in namespace `aipp` on node `dck8snode2` (healthy pods: `aipp-postgres-0`, `aipp-backend`, `aipp-frontend`).
- ✅ **UI Endpoint**: `http://aipp.dccloud.com` (Control Tower featuring 8 interactive tabs).
- ✅ **API Endpoint**: `http://api-aipp.dccloud.com/api/health` (`{"status":"ok"}`).
- ✅ **n8n Workflow Engine**: `https://n8n.dccloud.in.net` — **All 20/20 workflows deployed and active** (`00_error_sink` through `19_azure_network_watcher_audit`).
- ✅ **20-Repository Benchmark Sweep**: **20/20 Passed (100.0% Pass Rate)** across 9 programming ecosystems.
- ✅ **Master Final Deliverables**: Formatted and compiled in `final_deliverable/01_AIPP_Capstone_Project_Final_Report.docx` (2.75 MB).

---

## 1. What Has Been Completed & Verified (Up to v0.38.0)

1. **Modern Enterprise Cloud Architecture Diagram Suite**:
   - All architecture figures standardized to the **Modern Enterprise Cloud Architecture** format (white canvas, multi-tier layout, clean vector icons, red-glow security boundary box, crisp typography):
     - **Figure 7.1 — Master System Architecture (HLD · Hero View)**: Presentation Tier (8 tabs), FastAPI Gateway with Zero-Trust Security Boundary, LangGraph 8-Agent Mesh, PostgreSQL 15 / pgvector Dual Memory, and 11 MCP Integration Bus.
     - **Figure 7.2 — End-to-End Pipeline Generation & Validation Flow**: Generation-only boundary (decoupled from deployment triggers), ending with validated YAML emission and Git PR creation.
     - **Figure 7.3 — SRE Incident Triage, Chaos Resilience & Self-Healing RCA Flow**: 8-stage closed-loop SRE workflow (Live Alert → n8n Router → pgvector RAG → PipelineDoctor RCA → SRE DOCX Synthesis → PostgreSQL Sync → Slack Block-Kit Card → Closed-Loop Health).
     - **Figure 7.4 — Agent Run Lifecycle (LLD · State Machine)**: Formal FSM with Analyzing, Planning, Generating, Validating, 2-pass Self-Healing AST retry loop, and terminal states.
     - **Figure 7.5 — PostgreSQL 15 & pgvector Persistence Schema (LLD · ER Layer)**: Clean schema linking relational tables (`pipeline_runs`, `audit_logs`, `rca_reports`) with 1536-d HNSW cosine vector stores (`pipeline_embeddings`, `rca_embeddings`).

2. **100% Verbatim Chapter 8 Code Snippets & Codebase Audit**:
   - Fully audited and aligned all Chapter 8 code snippets with real files, exact line numbers, and authentic codebase logic (zero mock/fake data):
     - **Snippet 8.1**: `backend/api/pipelines.py` *(Lines 84–105)* — Rate/scope limit & `@router.post("/generate")`.
     - **Snippet 8.2**: `frontend/tabs/agent_trace.py` *(Lines 187–217)* — `build_tab()` with dropdown and Markdown trace renderer.
     - **Snippet 8.3**: `backend/mcp/guard.py` *(Lines 71–109)* & `backend/agents/skills.py` — `check(adapter)` Skill-Scope Guard.
     - **Snippet 8.4**: `backend/api/pipeline_doctor.py` *(Lines 58–77)* — 1536-d Cosine RAG retrieval and grounded `run_rca()`.
     - **Snippet 8.5**: `n8n/build_workflows.py` *(Lines 86–103)* — `cfg()` helper and inlined Slack/OpenAI credentials.
     - **Snippet 8.6**: `backend/validators/security_validator.py` *(Lines 9–23)* — `_DANGER` secret scanner patterns & `check()`.
     - **Snippet 8.7**: `backend/api/slack.py` *(Lines 75–105)* — `verify_slack_signature()` HMAC-SHA256 verifier.
     - **Snippet 8.8**: `docker-compose.yml` *(Lines 4–28 & 99–112)* — Multi-container Compose spec (`postgres`, `backend`, `frontend`, `n8n`).
     - **Snippet 8.9**: `scripts/reproduce.sh` *(Lines 1–25)* — Automated end-to-end benchmark reproduction script.

3. **Master Deliverables Synchronization & Cleanup**:
   - Deleted all obsolete interim drafts (`DEMO_AIPP_Capstone_Project_Final_Report.docx`).
   - Recompiled [`final_deliverable/01_AIPP_Capstone_Project_Final_Report.docx`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/final_deliverable/01_AIPP_Capstone_Project_Final_Report.docx) (2.75 MB) embedding all high-resolution modern diagrams and verified Chapter 8 snippets.

---

## 2. Standard Operational Commands

| Purpose | Command | Notes |
| :--- | :--- | :--- |
| **Sync .env to Live K8s** | `bash scripts/sync_secrets_to_k8s.sh` | Pushes updated keys from `.env` to K8s & reloads backend |
| **Run Chaos Test Suite** | `python3 scripts/test_all_workflows_chaos.py` | Queries live `aipp` pods; tests 20 workflows |
| **Rebuild All 20 n8n Workflows** | `python3 n8n/build_workflows.py` | Emits JSONs to `n8n/workflows/` |
| **Deploy Workflows to Live n8n** | `bash n8n/scripts/deploy.sh --activate-all` | Pushes to `https://n8n.dccloud.in.net` |
| **Recompile Capstone DOCX** | `python3 scripts/convert_paper.py` | Compiles Markdown to formatted `.docx` |
| **Run Reproduction Harness** | `bash scripts/reproduce.sh` | End-to-end evaluation reproduction script |
| **Run Unit Test Suite** | `pytest tests/unit/` | Validates models, generators, validators |
| **Run Backend Locally** | `uvicorn backend.server:app --host 0.0.0.0 --port 8001` | Native Python process |
| **Run Gradio UI Locally** | `python frontend/gradio_app.py` | Port 3300 mapping |

---

## 3. Architectural Boundaries & Developer Rules

- **MCP Adapter Pattern**: All external integrations (GitHub, GitLab, Azure DevOps, Harness, Tekton, K8s, AWS, GCP, Azure, n8n) must reside strictly in [`backend/mcp/`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/backend/mcp). Agents and routers must never make unstructured direct network calls.
- **Deterministic YAML Generation**: Pipelines must be produced via [`backend/generators/`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/backend/generators) to guarantee syntax validity and native task usage.
- **Security & Secret Redaction**: All logged outputs must strip secrets using `backend/core/logging.py:redact()`. Slack HITL interactions must enforce HMAC-SHA256 verification.
- **State Management**: Multi-agent orchestration flows through LangGraph (`StateGraph(AIPPState)`) in [`backend/orchestrator/`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/backend/orchestrator).
- **Architecture Visuals & Diagram Standards**: All system and workflow architecture diagrams must strictly follow the **Modern Enterprise Cloud Architecture** design standard (clean white canvas, multi-tier layout, official tech emblems, crisp typography, and red-highlighted security boundaries).
- **Deliverables Master Directory**: All official thesis and evaluation deliverables reside in [`final_deliverable/`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/final_deliverable) (which is ignored by Git).
- **Changelog & Documentation**: Keep [`CHANGELOG.md`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/CHANGELOG.md) synchronized when introducing new features.
