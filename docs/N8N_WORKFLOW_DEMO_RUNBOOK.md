# AIPP · n8n Workflow Suite Demonstration Runbook & User Guide

> **Production-Grade SRE & AI-Ops Platform User Guide**  
> *Target System*: AIPP Platform Control Tower & n8n Community Edition Engine  
> *AIPP Backend Endpoint*: `http://192.168.88.22:30801` (Kubernetes NodePort)  
> *n8n Instance*: `https://n8n.dccloud.in.net`  
> *UI Control Tower*: `http://aipp.dccloud.com` (or `http://192.168.88.22:30002`)

---

## 🏛️ 1. Architecture & Core Design Strategy

The AIPP n8n Workflow Suite comprises **20 production-shaped workflows** designed for Site Reliability Engineering (SRE), Platform Engineering, and Cloud Governance.

### Key Architectural Contracts:
1. **Secret-Vault Proxy Pattern**: n8n workflows hold **zero infrastructure secrets**. All cloud & infrastructure credentials (K8s tokens, GitHub PATs, Azure client secrets, Proxmox tokens, Grafana keys) live strictly inside the AIPP Backend. n8n calls `http://192.168.88.22:30801/api/proxy/*` with a single Bearer token (`AIPP_API_KEY`).
2. **Human-In-The-Loop (HITL) Slack Bridge**: Destructive actions (remediations, PR openings, VM provisioning, chaos injection) park at n8n `Wait` nodes. n8n generates interactive Slack cards with **`✅ Approve`** and **`❌ Reject`** buttons. Clicking a button sends an HMAC-SHA256 verified signal back to AIPP to resume workflow execution.
3. **100% n8n Community Edition Compatible**: Uses visual nodes only; zero dependency on Enterprise-only Variables API or custom JS code nodes.

---

## 📖 2. Complete 20 Workflow Catalog & User Guide

---

### 00 · AIPP · 00 · Error Sink
* **ID**: `6dIlL6fR1Gxh8xaY`
* **Trigger Type**: `n8n-nodes-base.errorTrigger` (Passive Error Handler)
* **HITL Approval**: N/A (Automated)
* **What it is**: The global exception handler for the entire n8n suite.
* **What it does**: Whenever any other workflow experiences an uncaught node failure, the Error Sink traps the error, redacts any sensitive strings using AIPP security redaction rules, formats a Slack alert card, and posts to `#aipp-alerts`.
* **How to Use**: Automatically active in the background. No manual invocation needed.

---

### 01 · AIPP · 01 · Azure Subscription Vending
* **ID**: `BPGQVXf49KYBgwar`
* **Trigger Type**: Webhook (`POST /webhook/aipp-sub-vending`)
* **HITL Approval**: 🛑 **YES** (Slack Card: Approve Landing Zone HCL)
* **What it is**: Automated Cloud Subscription & Landing Zone Vending Portal.
* **What it does**: Accepts subscription requests (team, cost center, region, tier). Prompts LLM to draft production Terraform HCL for landing zone network/storage. Sends a Slack HITL card to `#aipp-approvals`. Upon human approval, calls AIPP proxy (`POST /api/proxy/github/pr`) to open a Pull Request in repository `Subinoy2024/AIPP-AI-Driven-Pipeline-Platform-RACE`.
* **Sample Payload**:
  ```json
  {
    "team": "platform",
    "cost_center": "cc-42",
    "region": "eastus",
    "tier": "sandbox"
  }
  ```
* **How Users Use It**: Triggered via API call, Slack slash command, or developer portal request.

---

### 02 · AIPP · 02 · IaC Drift Detector
* **ID**: `KJ7M7K1fAJMOgBKq`
* **Trigger Type**: Schedule Cron (`0 */30 * * * *` - Every 30 minutes)
* **HITL Approval**: No (Automated Digest)
* **What it is**: Infrastructure-as-Code (IaC) Drift & Compliance Monitor.
* **What it does**: Periodically fetches main Git tree via AIPP proxy (`GET /api/proxy/github/tree/...`), scans Terraform state and Azure ARM configurations, uses AI to analyze infrastructure drift, and posts a drift summary to `#aipp-alerts`.
* **How Users Use It**: Automated background monitor. SREs receive proactive Slack alerts when cloud resources deviate from committed Git state.

---

### 03 · AIPP · 03 · Access Review Automator
* **ID**: `Ls36hg0qBCgfZqLm`
* **Trigger Type**: Schedule Cron (`0 9 * * 1` - Weekly Monday at 9 AM)
* **HITL Approval**: 🛑 **YES** (Slack Card: Certify Access List)
* **What it is**: ISO 27001 & SOC 2 Access Certification Automator.
* **What it does**: Fetches GitHub org members (`GET /api/proxy/github/org/Subinoy2024/members`) and Azure RBAC assignments. Uses LLM to identify stale or over-privileged accounts. Generates a Slack HITL access review card for SecOps approval.
* **How Users Use It**: SecOps leads review the weekly Slack card and click `Approve Certification` or `Revoke Stale Accounts`.

---

### 04 · AIPP · 04 · Developer Self-Service Portal
* **ID**: `RvydZDr9r96P0RIE`
* **Trigger Type**: Rendered Form Trigger (`POST /form/aipp-self-service-vm-request`)
* **HITL Approval**: 🛑 **YES** (Slack Card: Approve VM Provisioning)
* **What it is**: Developer Self-Service Infrastructure Provisioning Portal.
* **What it does**: Exposes an HTML form for developers to request virtual machines (Proxmox/Azure). Upon submission, requests Slack HITL approval from SREs. Once approved, issues a creation request via AIPP proxy (`POST /api/proxy/proxmox/vm`).
* **Rendered UI Link**: `https://n8n.dccloud.in.net/form/aipp-self-service-vm-request`
* **How Users Use It**: Developers open the form URL, specify workload requirements, and submit. SREs approve in Slack with one click.

---

### 05 · AIPP · 05 · Pipeline Status Digest
* **ID**: `j5d67wury8fHy376`
* **Trigger Type**: Schedule Cron (`0 17 * * 5` - Weekly Friday at 5 PM)
* **HITL Approval**: No (Automated Executive Summary)
* **What it is**: Multi-Platform CI/CD Pipeline Reliability Digest.
* **What it does**: Queries GitHub Actions (`GET /api/proxy/github/runs/...`) and Azure DevOps (`GET /api/proxy/ado/runs`), computes weekly build success rates, AI synthesizes top failure causes, and posts an executive digest to `#aipp-digest`.
* **How Users Use It**: Automated weekly briefing for Engineering Directors & DevOps leads.

---

### 06 · AIPP · 06 · K8s Health Scorecard
* **ID**: `9OdhkrZe1My4tSks`
* **Trigger Type**: Schedule Cron (`0 */4 * * *` - Every 4 hours)
* **HITL Approval**: No (Automated Scorecard)
* **What it is**: Kubernetes Cluster Reliability & Health Scorecard.
* **What it does**: Queries K8s pod statuses via AIPP proxy (`GET /api/proxy/k8s/pods?ns=prod`), calculates health score (0-100) based on restart counts & pod states. If health score drops below 80, sends an alert to `#aipp-alerts`.
* **How Users Use It**: Continuous background cluster health monitoring.

---

### 07 · AIPP · 07 · K8s Troubleshoot Assistant
* **ID**: `ZHI1Xbv0SZJc34w9`
* **Trigger Type**: Webhook (`POST /webhook/aipp-troubleshoot`)
* **HITL Approval**: 🛑 **YES** (Slack Card: Approve `kubectl` Fix)
* **What it is**: AI-Powered Kubernetes Diagnostic & Self-Healing Assistant.
* **What it does**: Receives failing pod details (e.g. `coredns-589f44dc88-7wnj5`). Queries pod details via proxy (`GET /api/proxy/k8s/pods/kube-system/coredns`), feeds logs to LLM for Root Cause Analysis (RCA), proposes exact `kubectl` fix commands, and requests Slack HITL approval before executing the fix.
* **Sample Payload**:
  ```json
  {
    "text": "pod=coredns-589f44dc88-7wnj5 ns=kube-system"
  }
  ```
* **How Users Use It**: Triggered automatically on K8s container crashes or invoked manually by SREs during live incidents.

---

### 08 · AIPP · 08 · Grafana Observability Auto-Remediator
* **ID**: `TgDIvtelce9C1bRe`
* **Trigger Type**: Webhook (`POST /webhook/aipp-grafana`)
* **HITL Approval**: 🛑 **YES** (Slack Card: Approve Observability Remediation)
* **What it is**: Automated Observability & Alert Remediation Engine.
* **What it does**: Receives Prometheus/Grafana firing alert webhooks (e.g. `HighMemoryUsage` on `api-checkout-1`). LLM selects optimal remediation strategy (`restart_pod`, `scale_hpa`, `clear_cache`). Prompts SRE in Slack for approval. Upon approval, posts remediation status back to `#aipp-alerts`.
* **Sample Payload**:
  ```json
  {
    "commonLabels": {"alertname": "HighMemoryUsage", "severity": "warning", "instance": "api-checkout-1"},
    "commonAnnotations": {"description": "container memory at 92%"},
    "alerts": [{"status": "firing", "labels": {"alertname": "HighMemoryUsage"}}]
  }
  ```
* **How Users Use It**: Set as the Webhook Notification Endpoint in Grafana Alerting rules.

---

### 09 · AIPP · 09 · Weekly Azure Cost Review
* **ID**: `LjvSinKqYwjmLdOr`
* **Trigger Type**: Schedule Cron (`0 8 * * 1` - Weekly Monday at 8 AM)
* **HITL Approval**: No (Automated Narrative)
* **What it is**: FinOps & Cloud Cost Optimization Advisor.
* **What it does**: Queries Azure Consumption API, analyzes cost spikes across resource groups, generates AI FinOps recommendations, and posts weekly cost narrative to `#aipp-digest`.
* **How Users Use It**: Automated Monday morning FinOps report for cloud budget managers.

---

### 10 · AIPP · 10 · Incident Commander Bot
* **ID**: `KKeRZ3bdX4lRCWZT`
* **Trigger Type**: Webhook (`POST /webhook/aipp-incident`)
* **HITL Approval**: No (Automated Triage & Escalation)
* **What it is**: Automated Incident Triage & On-Call Commander.
* **What it does**: Accepts incident alerts (`payments-svc latency spike`), classifies severity (P1/P2/P3), queries K8s cluster state via proxy (`GET /api/proxy/k8s/pods?ns=prod`), maps owning team via Service-Ownership map (`SVCMAP`), auto-assigns team, and drafts customer status page comms.
* **Sample Payload**:
  ```json
  {
    "summary": "payments-svc latency spike",
    "service_id": "payments-svc",
    "severity": "Sev2"
  }
  ```
* **How Users Use It**: Integrated into PagerDuty, Opsgenie, or manual incident creation hooks.

---

### 11 · AIPP · 11 · SOP / Runbook Generator
* **ID**: `FHCUlCNnHelcncky`
* **Trigger Type**: Webhook (`POST /webhook/aipp-sop`)
* **HITL Approval**: No (Automated Document Generation)
* **What it is**: Enterprise Post-Mortem & SOP Runbook Generator.
* **What it does**: Called when an incident is closed. Calls AIPP backend (`POST /api/workflows/rca/docx`) to synthesize an enterprise Microsoft Word (`.docx`) post-mortem document. Drafts Markdown SOP via LLM and posts download links & previews to `#aipp-approvals`.
* **Sample Payload**:
  ```json
  {
    "incident_id": "INC-42",
    "rca_summary": "payments latency spike resolved by restart",
    "runbook_topic": "payments-svc restart"
  }
  ```
* **How Users Use It**: Automatically triggered when resolving an incident to generate compliance documentation.

---

### 12 · AIPP · 12 · Azure SLO Burn-Rate Monitor
* **ID**: `VN9FX7bGKhlMq8Qz`
* **Trigger Type**: Schedule Cron (`*/5 * * * *` - Every 5 minutes)
* **HITL Approval**: No (Automated Decisioning)
* **What it is**: Service Level Objective (SLO) Error Budget Monitor.
* **What it does**: Queries Azure Monitor metrics for failed requests every 5 minutes. Evaluates error budget burn rate. LLM decides whether to page on-call (fast burn), open a ticket (slow burn), or remain silent.
* **How Users Use It**: Continuous background SLO monitoring.

---

### 13 · AIPP · 13 · DR Readiness Drill Scheduler
* **ID**: `kSzQf5nIagmDXMu1`
* **Trigger Type**: Schedule Cron (`0 2 1 * *` - Monthly on 1st at 2 AM)
* **HITL Approval**: 🛑 **YES** (Slack Card: Confirm DR Drill Execution)
* **What it is**: Disaster Recovery (DR) Drill & Resilience Scheduler.
* **What it does**: Generates monthly DR drill scenario (failover test, database restore). AI creates step-by-step checklist and posts Slack HITL card for SRE Lead confirmation before initiating drill.
* **How Users Use It**: SRE Leads review monthly DR scenarios and confirm drill schedules via Slack.

---

### 14 · AIPP · 14 · Chaos Engineering Assistant
* **ID**: `VgQAxJ9hYXOeVVIH`
* **Trigger Type**: Rendered Form Trigger (`POST /form/aipp-chaos-experiment-request`)
* **HITL Approval**: 🛑 **YES** (Slack Card: Authorize Chaos Experiment)
* **What it is**: Self-Service Resilience & Chaos Experiment Portal.
* **What it does**: Exposes a web form for engineers to request chaos experiments (pod deletion, latency injection). AI drafts Chaos Mesh spec. Asks SRE Lead HITL approval before injecting fault into target namespace.
* **Rendered UI Link**: `https://n8n.dccloud.in.net/form/aipp-chaos-experiment-request`
* **How Users Use It**: Engineers submit chaos hypothesis via form; SREs authorize fault injection in Slack.

---

### 15 · AIPP · 15 · Log Anomaly Hunter
* **ID**: `wTU98Qic306zusIk`
* **Trigger Type**: Schedule Cron (`0 */2 * * *` - Every 2 hours)
* **HITL Approval**: No (Automated Anomaly Alerts)
* **What it is**: Vector-Search Log Anomaly & Pattern Hunter.
* **What it does**: Scans application logs every 2 hours using cosine vector similarity search. Identifies novel error clusters and unhandled exceptions, alerting `#aipp-alerts` before users report issues.
* **How Users Use It**: Automated proactive anomaly detection.

---

### 16 · AIPP · 16 · Pipeline Review Gate (HITL)
* **ID**: `T5W8osBVzDNpdb0j`
* **Trigger Type**: Webhook (`POST /webhook/aipp-pipeline-review`)
* **HITL Approval**: 🛑 **YES** (Slack Card: Approve Pipeline Deployment)
* **What it is**: Multi-Cloud CI/CD Pipeline Security & Compliance Gate.
* **What it does**: Receives generated CI/CD pipeline YAML. LLM audits YAML for security risks (unpinned actions, root execution, missing secret redaction). Posts interactive Slack card with **`✅ Approve`** and **`❌ Reject`** buttons. Unlocks deployment upon approval.
* **Sample Payload**:
  ```json
  {
    "run_id": "demo-101",
    "pipeline_yaml": "stages:\n  - build\n  - deploy",
    "targets": ["aws", "azure"]
  }
  ```
* **How Users Use It**: Called by AIPP Multi-Agent Orchestrator before committing generated pipeline YAML to repository.

---

### 17 · AIPP · 17 · Azure VM Health & Auto-Healer
* **ID**: `cMpVhaimjSdUxFK1`
* **Trigger Type**: Schedule Cron (`*/15 * * * *` - Every 15 minutes)
* **HITL Approval**: 🛑 **YES** (Slack Card: Approve VM Restart)
* **What it is**: Cloud VM Health Monitor & Auto-Healer.
* **What it does**: Checks Azure VM status every 15 minutes via AIPP proxy. If a VM is stopped or degraded, AI calculates business impact and requests Slack HITL approval to issue restart command.
* **How Users Use It**: Automated background VM remediation.

---

### 18 · AIPP · 18 · Azure Storage Capacity Monitor
* **ID**: `UYOt5Sia4rtyKRU1`
* **Trigger Type**: Schedule Cron (`0 6 * * *` - Daily at 6 AM)
* **HITL Approval**: No (Automated Capacity Alerts)
* **What it is**: Cloud Storage Quota & Lifecycle Monitor.
* **What it does**: Checks Azure Storage Accounts daily via proxy (`GET /api/proxy/...`). If capacity exceeds 85%, AI calculates days to exhaustion and posts lifecycle recommendations to `#aipp-alerts`.
* **How Users Use It**: Automated daily storage capacity report.

---

### 19 · AIPP · 19 · Azure Network Watcher Audit
* **ID**: `qhFYC832VlVc73n3`
* **Trigger Type**: Schedule Cron (`0 3 * * 0` - Weekly Sunday at 3 AM)
* **HITL Approval**: No (Automated Audit Report)
* **What it is**: Cloud Network Security & NSG Audit Guard.
* **What it does**: Scans Azure Network Security Groups (NSGs) weekly for risky open ports (e.g. 0.0.0.0/0 on port 22/3389). AI flags security vulnerabilities and posts compliance audit card to `#aipp-alerts`.
* **How Users Use It**: Weekly automated network security audit.

---

## 🎬 3. Step-by-Step Live Demonstration Walkthrough

When presenting AIPP to clients or stakeholders, follow this **3-Step Demonstration Guide**:

### Step 1: Execute Automated Demo Suite
Run the automated test runner in terminal to trigger all webhooks and verify API health:
```bash
python3 n8n/scripts/demo_suite.py
```

### Step 2: Showcase Interactive Human-In-The-Loop (HITL) Slack Cards
1. Open `#aipp-approvals` in Slack.
2. Observe the interactive Block Kit cards generated by **Workflow 01** (Subscription Vending), **Workflow 07** (K8s Troubleshoot), **Workflow 08** (Grafana Remediation), and **Workflow 16** (Pipeline Gate).
3. Click **`✅ Approve`**. Watch the card instantly update to green (`Approved by SRE`) and notice execution resuming in n8n.

### Step 3: Showcase Self-Service Web Forms
1. Open `https://n8n.dccloud.in.net/form/aipp-self-service-vm-request` in a browser.
2. Enter email (`demo@aipp.local`) and target (`Proxmox / Azure`).
3. Click **Submit** and show how the request instantly lands in Slack for manager sign-off.

---

## 📊 Summary Matrix

| Workflow ID | Workflow Name | Trigger Mechanism | HITL Gate | AIPP Proxy Target |
| :--- | :--- | :--- | :--- | :--- |
| `6dIlL6fR1Gxh8xaY` | **00 · Error Sink** | Error Trigger | No | Secret Redactor |
| `BPGQVXf49KYBgwar` | **01 · Azure Subscription Vending** | Webhook | 🛑 YES | `/api/proxy/github/pr` |
| `KJ7M7K1fAJMOgBKq` | **02 · IaC Drift Detector** | Schedule (30m) | No | `/api/proxy/github/tree` |
| `Ls36hg0qBCgfZqLm` | **03 · Access Review Automator** | Schedule (Weekly) | 🛑 YES | `/api/proxy/github/org` |
| `RvydZDr9r96P0RIE` | **04 · Developer Self-Service Portal** | Rendered Form | 🛑 YES | `/api/proxy/proxmox/vm` |
| `j5d67wury8fHy376` | **05 · Pipeline Status Digest** | Schedule (Weekly) | No | `/api/proxy/ado/runs` |
| `9OdhkrZe1My4tSks` | **06 · K8s Health Scorecard** | Schedule (4h) | No | `/api/proxy/k8s/pods` |
| `ZHI1Xbv0SZJc34w9` | **07 · K8s Troubleshoot Assistant** | Webhook | 🛑 YES | `/api/proxy/k8s/pods` |
| `TgDIvtelce9C1bRe` | **08 · Grafana Auto-Remediator** | Webhook | 🛑 YES | `/api/proxy/grafana/alerts` |
| `LjvSinKqYwjmLdOr` | **09 · Weekly Azure Cost Review** | Schedule (Weekly) | No | Azure Cost Management |
| `KKeRZ3bdX4lRCWZT` | **10 · Incident Commander Bot** | Webhook | No | `/api/proxy/k8s/pods` |
| `FHCUlCNnHelcncky` | **11 · SOP / Runbook Generator** | Webhook | No | `/api/workflows/rca/docx` |
| `VN9FX7bGKhlMq8Qz` | **12 · Azure SLO Burn-Rate Monitor** | Schedule (5m) | No | Azure Monitor Metrics |
| `kSzQf5nIagmDXMu1` | **13 · DR Readiness Drill Scheduler** | Schedule (Monthly) | 🛑 YES | SRE Checklist |
| `VgQAxJ9hYXOeVVIH` | **14 · Chaos Engineering Assistant** | Rendered Form | 🛑 YES | K8s Chaos Mesh |
| `wTU98Qic306zusIk` | **15 · Log Anomaly Hunter** | Schedule (2h) | No | Log Analytics Vector Search |
| `T5W8osBVzDNpdb0j` | **16 · Pipeline Review Gate (HITL)** | Webhook | 🛑 YES | AIPP Orchestrator Gate |
| `cMpVhaimjSdUxFK1` | **17 · Azure VM Health & Auto-Healer** | Schedule (15m) | 🛑 YES | Azure Resource Groups |
| `UYOt5Sia4rtyKRU1` | **18 · Azure Storage Capacity Monitor** | Schedule (Daily) | No | Azure Storage Accounts |
| `qhFYC832VlVc73n3` | **19 · Azure Network Watcher Audit** | Schedule (Weekly) | No | Azure Network Security |
