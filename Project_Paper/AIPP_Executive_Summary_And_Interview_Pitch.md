# AIPP — AUTOMATED PIPELINE PLATFORM
## Executive System Architecture Summary & Technical Interview Guide

---

### 🚀 1. Executive System Architecture Summary (Client & Interview Elevator Pitch)

> **AIPP (Automated Pipeline Platform)** is an enterprise AI-Ops platform deployed on **Kubernetes** that automates repository-aware CI/CD pipeline synthesis, build log root-cause analysis, and SRE operations across 5 major platform engines (**Azure DevOps, GitHub Actions, GitLab CI, Harness, Tekton**) and 3 cloud providers (**Azure, AWS, GCP**). The system connects a **Gradio 4 Control Tower** to an asynchronous **FastAPI backend** that orchestrates an 8-agent **LangGraph state machine**; the agents inspect repository code, determine multi-stage architecture, and invoke deterministic Python generators to produce 100% syntactically valid YAML files with embedded Open Policy Agent (OPA) security gates. All external API calls (GitHub, Azure, AWS, GCP, K8s) pass through a **Model Context Protocol (MCP) Secret-Vault Proxy** that encrypts tokens at rest via Fernet AES-128 and redacts secrets from logs, while **PostgreSQL with pgvector** maintains historical incident memory for sub-second RAG log diagnosis. To automate Site Reliability Engineering tasks without risking unauthorized production changes, AIPP integrates **17 n8n AI-Ops workflows** that execute background cluster health checks, drift scans, and incident triaging, parking risky remediations at **Slack Block Kit Human-In-The-Loop (HITL)** approval gates guarded by HMAC-SHA256 cryptographic signatures that record immutable ISO 27001 audit trails upon sign-off.

---

### 🏛️ 2. Core Service Connections & System Interaction Architecture

```
                          ┌────────────────────────────────────────────────────────┐
                          │                GRADIO 4 CONTROL TOWER                  │
                          │             (Frontend UI · 10 Interactive Tabs)        │
                          └───────────────────────────┬────────────────────────────┘
                                                      │ HTTP / SSE REST API
                                                      ▼
                          ┌────────────────────────────────────────────────────────┐
                          │                 FASTAPI BACKEND SERVER                 │
                          │             (Routing, Security, Rate Limiter)          │
                          └───────┬───────────────────┬────────────────────┬───────┘
                                  │                   │                    │
            ┌─────────────────────┘                   │                    └─────────────────────┐
            ▼                                         ▼                                          ▼
┌──────────────────────┐                  ┌──────────────────────┐                   ┌──────────────────────┐
│  LangGraph Multi-    │                  │  PipelineDoctor RAG  │                   │ Secret Proxy Guard   │
│  Agent Orchestrator  │                  │  Incident Search     │                   │  (11 MCP Adapters)   │
│  (8 Micro-Agents)    │                  │  (pgvector HNSW)     │                   │  (Fernet AES-128)    │
└───────────┬──────────┘                  └───────────┬──────────┘                   └───────────┬──────────┘
            │                                         │                                          │
            └─────────────────────┬───────────────────┘                                          │
                                  ▼                                                              ▼
                   ┌──────────────────────────────┐                              ┌──────────────────────────────┐
                   │    PostgreSQL + pgvector DB   │                              │     n8n Workflow Engine    │
                   │ (Audit Logs / RAG Embeddings)│                              │   (17 AI-Ops Workflows)    │
                   └──────────────────────────────┘                              └──────────────┬───────────────┘
                                                                                                │ Slack Webhooks
                                                                                                ▼
                                                                                 ┌──────────────────────────────┐
                                                                                 │    Slack HITL Bridge         │
                                                                                 │  (Block Kit Approve/Reject)  │
                                                                                 └──────────────────────────────┘
```

---

### 🎙️ 3. Key Interview Speaking Points (Client & Technical Q&A)

#### Question 1: How was the application built, and how do the micro-agents operate?
* **Answer**: *"AIPP uses a hybrid dual-layer architecture built with **FastAPI**, **Gradio 4**, and **LangGraph**. An 8-agent state graph (`StateGraph(AIPPState)`) executes in-process micro-agents for repository analysis, technology detection, architecture discovery, pipeline planning, and validation. To eliminate raw LLM syntax hallucinations, the agents pass structured JSON plans to **deterministic Python code generators** that emit 100% syntactically valid YAML files with native platform task types (such as `TerraformTaskV2@2` for Azure DevOps or `hashicorp/setup-terraform@v3` for GitHub Actions)."*

#### Question 2: What is the role of n8n in your platform?
* **Answer**: *"We integrated **n8n Community Edition** as our autonomous AI-Ops workflow engine. We built **17 production n8n workflows** covering SRE operations—including Azure subscription vending, IaC drift detection, Kubernetes cluster health scorecards, Grafana alert auto-remediation, and cloud cost reviews. n8n allows us to decouple event-driven background automation from our primary FastAPI backend while providing visual workflow management."*

#### Question 3: How do you handle security, authentication, and Human-In-The-Loop (HITL) approvals?
* **Answer**: *"We enforce security across three layers:*
  1. * **Secret-Vault Proxy & Fernet Encryption**: n8n workflows and LLMs hold **zero external credentials**. API requests are routed through `/api/proxy/*` where server-side encrypted tokens (**Fernet AES-128**) are injected and secrets are redacted from return logs.
  2. * **Slack Block Kit HITL Gates**: High-risk workflows park execution at n8n `Wait` nodes and post interactive Slack cards with green **`Approve`** and red **`Reject`** buttons.
  3. * **HMAC-SHA256 Cryptographic Verification**: User clicks hit `/api/slack/interactions` where requests are validated using **HMAC-SHA256 signatures** and a 5-minute timestamp window before resuming n8n and appending an entry to our **PostgreSQL ISO 27001 audit ledger**."*

#### Question 4: How does the PipelineDoctor log analysis engine work?
* **Answer**: *"PipelineDoctor provides evidence-grounded failure log diagnosis using **RAG (Retrieval-Augmented Generation)**. Raw failure logs are embedded into 1536-dimensional vectors using OpenAI `text-embedding-3-small`. We query **PostgreSQL pgvector** using **HNSW cosine distance** to surface the top 3 similar past resolved incidents. Prepending these past resolutions into the LLM prompt enables sub-second root-cause analysis with high diagnostic accuracy."*

---

### 📊 4. System Telemetry & Benchmark Verification Summary

* **20-Repository Benchmark Sweep**: **100.0% Pass Rate (20 / 20 open-source repositories passed)** across 9 ecosystems (Java, .NET, Python, Go, Node.js, React/Next, Vue.js, Rust, C++, Ruby, PHP).
* **Self-Healing JSON Repair Engine**: `_repair_json()` automatically cleans unescaped control characters, raw newlines, and trailing commas from LLM outputs.
* **Operational Cost**: **$0.0387 USD total LLM spend** (~$0.0019 USD per pipeline generation) using OpenAI `gpt-4o-mini`.
* **n8n Workflow Execution Latency**: **Sub-second execution latency ($\approx 0.30$s)** across all 17 AI-Ops workflows.
