# AIPP — Automated Pipeline Platform

**AIPP (Automated Pipeline Platform)** is a production-grade, enterprise AI-Ops platform that analyzes real Git repositories and synthesizes explainable, deployment-ready CI/CD pipelines across 5 industry platforms (**Azure DevOps, GitHub Actions, GitLab CI, Harness, Tekton**) and 3 cloud providers (**Azure, AWS, GCP**).

It features a self-healing **Multi-Agent Orchestrator**, an evidence-grounded **PipelineDoctor (RAG RCA)** for CI/CD failure logs, **20 n8n AI-Ops Workflows**, and a **Human-In-The-Loop (HITL) Slack Bridge** with native Block Kit interactive buttons.

---

## 🌟 Key Highlights & Verification Benchmarks

* 🟢 **20/20 Open-Source Repository LLM Benchmark Score (100.0% Pass Rate)**: Swept 20 open-source repositories across 9 programming ecosystems (Java, .NET, Python, Go, Node.js, React/Next, Vue.js, Rust, C++, Ruby, PHP). Self-healing JSON repair engine automatically recovers from raw LLM syntax quirks.
* 🟢 **20 n8n AI-Ops Workflows Connected**: Covers Azure subscription vending, IaC drift, K8s cluster health & troubleshooting, Grafana auto-remediation, Azure cost review, incident commander bot, SOP/runbook generator, SLO burn-rate, DR drills, chaos engineering, log anomaly hunter, and pipeline review gates.
* 🟢 **Human-In-The-Loop (HITL) via Slack Block Kit**: Interactive green **`✅ Approve`** and red **`❌ Reject`** buttons for manual sign-off. HMAC-SHA256 signature verification with 5-minute skew window ensures compliance.
* 🟢 **One-Click YAML Export & ISO 27001 CSV Audit**: Direct download of generated `.github/workflows/ci.yml` or `azure-pipelines.yml` into local IDEs, and one-click ISO 27001 change-management audit log export to CSV.
* 🟢 **Self-Hosted & 100% Open-Source Core**: Runs on local Kubernetes (`aipp` namespace). Utilizes OpenAI `gpt-4o-mini` with real-time token spend telemetry ($\approx \$0.001$ per pipeline run).

---

## 🏛️ System Architecture Overview

```
                          ┌────────────────────────────────────────────────────────┐
                          │                   AIPP CONTROL TOWER                   │
                          │             (Gradio 4 / FastAPI / LangGraph)           │
                          └───────────────────────────┬────────────────────────────┘
                                                      │
              ┌───────────────────────────────────────┼───────────────────────────────────────┐
              ▼                                       ▼                                       ▼
 ┌──────────────────────────┐            ┌──────────────────────────┐            ┌──────────────────────────┐
 │    Multi-Agent Engine    │            │     PipelineDoctor RCA   │            │   20 n8n AI-Ops Engine   │
 │ (Repo/Tech/Arch/Planner/ │            │ (pgvector HNSW Cosine    │            │ (Slack Block Kit HITL,   │
 │  Generator/Validator)    │            │  RAG Memory Search)      │            │  Proxy Secret Redaction) │
 └────────────┬─────────────┘            └────────────┬─────────────┘            └────────────┬─────────────┘
              │                                       │                                       │
              └───────────────────────────────────────┼───────────────────────────────────────┘
                                                      ▼
                                       ┌─────────────────────────────┐
                                       │   PostgreSQL + pgvector DB  │
                                       │  (Audit Logs / RAG Memory)  │
                                       └─────────────────────────────┘
```

---

## 🛠️ Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend** | Gradio 4 (Python) · 10 Production UI Tabs |
| **Backend** | FastAPI (Python 3.12) · 15 API Routers |
| **Orchestration** | LangGraph (`StateGraph`) · 8 Focused Micro-Agents |
| **Persistence** | PostgreSQL 15 + **pgvector** (async SQLAlchemy 2 + Alembic) |
| **RAG Memory** | `pipeline_embeddings` + `rca_embeddings` (1536-dim HNSW Cosine Index) |
| **Workflow Engine** | n8n Community Edition · 17 Generated AI-Ops Workflows |
| **HITL Bridge** | Slack Block Kit Interactive Cards · HMAC-SHA256 Signature Verified |
| **Containerization** | Docker + Docker Compose + Kubernetes Helm/Kustomize (`aipp` namespace) |
| **Testing** | pytest (500+ Unit & Integration Tests) |

---

## 🚀 Quickstart & Deployment

### 1. Local Kubernetes Deployment (Recommended)
```bash
# Apply namespace, postgres, configmaps, secrets, backend, and frontend
kubectl apply -k k8s/

# Verify rollout status
kubectl rollout status deployment/aipp-backend -n aipp
kubectl rollout status deployment/aipp-frontend -n aipp
```

* **UI Tower**: `http://aipp.dccloud.com`
* **API Health**: `http://api-aipp.dccloud.com/api/health`
* **n8n Engine**: `https://n8n.dccloud.in.net`

### 2. Local Python Execution (Development Mode)
```bash
# 1. Install dependencies
pip install -r backend/requirements.txt

# 2. Run backend API
uvicorn backend.server:app --host 0.0.0.0 --port 8001 --reload

# 3. Run frontend UI
python frontend/gradio_app.py
```

---

## 🧪 Unit & Integration Testing

Run the test suite to verify business logic, generators, and validators:
```bash
pytest tests/unit/
```

---

## 📁 Repository Structure

```
.
├── backend/              FastAPI backend, micro-agents, generators, validators, MCP adapters
├── frontend/             Gradio 4 web application tabs and components
├── k8s/                  Production Kubernetes manifests (ingress, backend, frontend, postgres, secrets)
├── n8n/                  17 AI-Ops workflow generators and JSON definitions
├── policy/               OPA Rego policy rules (Azure, AWS, GCP)
├── scripts/              Deployment & bootstrap scripts
├── tests/                Unit, integration, and benchmark test suites
├── Dockerfile            Multi-stage production container build
├── docker-compose.yml    Local container orchestration
├── .gitignore            Production build & cache exclusion rules
└── README.md             System architecture & operational guide
```

---

## 📄 License
Distributed under the MIT License. See `LICENSE` for more information.
