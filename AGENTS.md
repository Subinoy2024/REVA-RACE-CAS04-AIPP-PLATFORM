# AGENTS.md · Developer & AI Assistant Guidelines

This document provides context, architectural boundaries, verified milestones, runtime preferences, and current progress state for AI assistants (like Antigravity / Gemini) and human developers working on **AIPP (Automated Pipeline Platform)**.

---

## 0. Current System State & Verified Milestones

- ✅ **Local Kubernetes Cluster**: Deployed in namespace `aipp` on node `dck8snode2` (healthy pods: `aipp-postgres-0`, `aipp-backend`, `aipp-frontend`).
- ✅ **UI Endpoint**: `http://aipp.dccloud.com` (Control Tower featuring 8 interactive tabs).
- ✅ **API Endpoint**: `http://api-aipp.dccloud.com/api/health` (`{"status":"ok"}`).
- ✅ **n8n Workflow Engine**: `https://n8n.dccloud.in.net` — **All 20/20 workflows deployed and active** (`00_error_sink` through `19_azure_network_watcher_audit`).
- ✅ **20-Repository Benchmark Sweep**: **20/20 Passed (100.0% Pass Rate)** across 9 programming ecosystems.

---

## 1. What Has Been Completed & Verified (Up to v0.37.1)

1. **Dynamic Live Kubernetes Infrastructure Discovery**:
   - Refactored `scripts/test_all_workflows_chaos.py` and `n8n/scripts/demo_suite.py` with `discover_live_k8s_infra(namespace="aipp")`.
   - Test suites automatically query live cluster pods via `kubectl` and inject real pod names, restart counts, and dynamic timestamped incident IDs (e.g. `INC-20260828-XXXX`).

2. **Real-Time PostgreSQL Database Sync & pgvector RCA Memory**:
   - Backend endpoint [`POST /api/workflows/rca/docx`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/backend/api/workflows.py) automatically synchronizes:
     - **`audit_logs`**: Immutable event (`sre.rca.docx.generated`) with incident ID, commander, and download path.
     - **`rca_reports`**: Structured incident post-mortem data.
     - **`rca_embeddings`**: 1536-dimensional pgvector cosine embeddings (`embed_and_persist`) so `PipelineDoctor` learns from every incident.
   - **Workflow 11 (`11_sop__runbook_generator`)**: Directly wired to `POST /api/workflows/rca/docx` for synchronous database persistence upon incident triage/closure.

3. **Topic-Aware & SRE Severity-Gated SOP Generation (Workflow 11)**:
   - Added `Extract Incident Context` node parsing alert topics, impacted pods, and root causes.
   - Added `Critical or Closed?` conditional branch generating full `.docx` post-mortems for P1/Critical incidents, while routing lower-severity alerts to lightweight digests.

4. **Control Tower Documentation & Defense Reference**:
   - Created [`docs/AIPP_UI_TABS_REFERENCE_GUIDE.md`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/docs/AIPP_UI_TABS_REFERENCE_GUIDE.md) detailing **WHY, WHAT, HOW**, and **Defense Q&A** for all 8 UI tabs.
   - Synchronized [`docs/AIPP_Architecture.drawio`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/docs/AIPP_Architecture.drawio).

5. **Capstone Final Report Updated & Recompiled**:
   - Updated [`Project_Paper/AIPP_Final_Capstone_Project_Report.md`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/Project_Paper/AIPP_Final_Capstone_Project_Report.md) with 20 n8n workflows, Section 8.7 database sync, and live cluster discovery.
   - Recompiled [`Project_Paper/AIPP_Final_Capstone_Project_Report.docx`](file:///Users/subdebna/CAS-04-MS-SUBINOY-AIPP/REVA-RACE-CAS04-AIPP-PLATFORM/Project_Paper/AIPP_Final_Capstone_Project_Report.docx) (1.83 MB) and synced to `docs/`.

---

## 2. Standard Operational Commands

| Purpose | Command | Notes |
| :--- | :--- | :--- |
| **Sync .env to Live K8s** | `bash scripts/sync_secrets_to_k8s.sh` | Pushes updated keys from `.env` to K8s & reloads backend |
| **Run Chaos Test Suite** | `python3 scripts/test_all_workflows_chaos.py` | Queries live `aipp` pods; tests 20 workflows |
| **Rebuild All 20 n8n Workflows** | `python3 n8n/build_workflows.py` | Emits JSONs to `n8n/workflows/` |
| **Deploy Workflows to Live n8n** | `bash n8n/scripts/deploy.sh --activate-all` | Pushes to `https://n8n.dccloud.in.net` |
| **Recompile Capstone DOCX** | `python3 scripts/convert_paper.py` | Compiles Markdown to formatted `.docx` |
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
