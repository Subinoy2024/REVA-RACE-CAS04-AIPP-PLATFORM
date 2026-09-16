# AIPP — Automated Pipeline Platform

**AIPP (Automated Pipeline Platform)** is a production-grade, enterprise AI-Ops platform that analyzes real Git repositories and synthesizes explainable, deployment-ready CI/CD pipelines across 5 industry platforms (**Azure DevOps, GitHub Actions, GitLab CI, Harness, Tekton**) and 3 cloud providers (**Azure, AWS, GCP**).

It features a self-healing **Multi-Agent Orchestrator**, an evidence-grounded **PipelineDoctor (RAG RCA)** for CI/CD failure logs, a **Multi-Gate Policy Enforcement Engine** (AST linters + OPA Rego), and a **Human-In-The-Loop (HITL) Slack Bridge** backed by n8n SRE automation.

---

## 🌟 Key Highlights & Verification Benchmarks

* 🟢 **Multi-Cloud CI/CD Pipeline Generator (100.0% Pass Rate)**: Swept 20 open-source repositories across 9 programming ecosystems (Java, .NET, Python, Go, Node.js, React/Next, Vue.js, Rust, C++, Ruby, PHP). Self-healing AST repair engine automatically recovers from syntax and schema anomalies.
* 🟢 **PipelineDoctor Root Cause Analysis (pgvector RAG RCA)**: Evaluated against 50 real CI/CD incident logs, retrieving grounded failure context via 1536-dimensional HNSW cosine embeddings to achieve an $F_1$ score of 0.898 (outperforming raw LLM baselines at $p < 0.01$).
* 🟢 **20 n8n AI-Ops Workflows Connected**: Automates SRE incident triage, K8s cluster health & troubleshooting, IaC drift, Grafana remediation, chaos drills, log anomaly hunting, cost audits, and approval gating.
* 🟢 **Multi-Gate Policy & Security Governance**: Enforces 4 AST validation passes, secret leak scanners, and 12 Open Policy Agent (OPA) Rego policy constraints prior to emitting deployment artifacts.
* 🟢 **Human-In-The-Loop (HITL) Governance via Slack**: Interactive green **`✅ Approve`** and red **`❌ Reject`** Block Kit cards with HMAC-SHA256 signature verification and n8n webhook routing.
* 🟢 **Self-Hosted & Kubernetes-Native**: Deployed in namespace `aipp` on node `dck8snode2`. Powered by OpenAI `gpt-4o-mini` with token spend telemetry ($\approx \$0.001$ per pipeline run).

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
| **Frontend** | Gradio 4 (Python) · 8 Interactive Control Tower Tabs |
| **Backend** | FastAPI (Python 3.12) · 15 API Routers |
| **Orchestration** | LangGraph (`StateGraph`) · 8 Focused Micro-Agents |
| **Persistence** | PostgreSQL 15 + **pgvector** (async SQLAlchemy 2 + Alembic) |
| **RAG Memory** | `pipeline_embeddings` + `rca_embeddings` (1536-dim HNSW Cosine Index) |
| **Workflow Engine** | n8n Community Edition · 20 Connected SRE & HITL Workflows |
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

* **UI Tower (Intranet / HTTP)**: `http://aipp.dccloud.com`
* **UI Tower (Public / HTTPS)**: `https://aipp.dccloud.in.net`
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
├── n8n/                  20 AI-Ops workflow generators and JSON definitions
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
