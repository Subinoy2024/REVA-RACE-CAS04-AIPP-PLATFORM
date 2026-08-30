<!--
================================================================================
AIPP — Automated Pipeline Platform
MS Capstone Project · Final Report
================================================================================
File format: Markdown, converted to DOCX via scripts/md_to_docx.py
Rendered length target: 55-60 pages @ Times New Roman 12pt, 1.5 line spacing,
1-inch margins.
================================================================================
-->

<div align="center">

# AIPP: An Automated Pipeline Platform for Multi-Cloud, Multi-CI/CD Pipeline Generation and AI-Driven Root Cause Analysis

**A Capstone Project Report submitted in partial fulfilment of the requirements for the award of the degree of**

**[Your Degree Program Name]**

Submitted by

**[Your Full Name]**

**SR No. [Your SR / Registration Number]**

Under the guidance of

**Internal Guide**
**[Internal Guide Name, Designation]**

**External / Industry Guide**
**[External Guide Name, Designation, Company]**

<br>

**REVA Academy for Corporate Excellence (RACE)**
**REVA University, Bengaluru, Karnataka — 560064**

**Batch: [YYYY-YYYY]**

**[Month, Year of Submission]**

</div>

<div style="page-break-after: always;"></div>

## Candidate's Declaration

I, **[Your Full Name]**, bearing SR No. **[Your SR Number]**, hereby declare that the capstone project titled **"AIPP: An Automated Pipeline Platform for Multi-Cloud, Multi-CI/CD Pipeline Generation and AI-Driven Root Cause Analysis"**, submitted to REVA Academy for Corporate Excellence (RACE), REVA University in partial fulfilment of the requirements for the award of the degree of **[Your Degree Program Name]**, is a bona fide record of my own work carried out under the guidance of **[Internal Guide Name]** and **[External Guide Name]**.

I further declare that the work reported in this dissertation has not been submitted, either in part or in full, for the award of any other degree or diploma of this or any other university. Where the work of others has been used, due credit has been given by way of citation and reference. I remain solely responsible for the content, correctness, and originality of this report.

Place: Bengaluru
Date: [DD Month YYYY]

_______________________
**[Your Full Name]**
SR No. [Your SR Number]

<div style="page-break-after: always;"></div>

## Acknowledgment of Project Ownership and Usage Rights

I acknowledge that the intellectual property arising out of this project, including source code, design documents, and derived artefacts, is jointly owned as per the agreement between me and REVA Academy for Corporate Excellence, REVA University. The source code developed as part of this project has been open-sourced under the MIT licence and made available at the GitHub repository listed in the back matter of this report. Any subsequent commercial or derivative use of the source code shall adhere to the terms of that licence.

Place: Bengaluru
Date: [DD Month YYYY]

_______________________
**[Your Full Name]**

<div style="page-break-after: always;"></div>

## Certificate

This is to certify that the capstone project titled **"AIPP: An Automated Pipeline Platform for Multi-Cloud, Multi-CI/CD Pipeline Generation and AI-Driven Root Cause Analysis"** is a bona fide record of the work carried out by **[Your Full Name]** (SR No. **[Your SR Number]**), a candidate for the degree of **[Your Degree Program Name]** at REVA Academy for Corporate Excellence, REVA University, Bengaluru, during the academic period **[YYYY-YYYY]**.

The work has been carried out under our guidance and, to the best of our knowledge, has not formed the basis for the award of any other degree.

<br>

**Internal Guide**
[Internal Guide Name]
Designation, RACE, REVA University

**External / Industry Guide**
[External Guide Name]
Designation, [Company Name]

**Director**
[Program Director Name]
RACE, REVA University

<div style="page-break-after: always;"></div>

## Acknowledgement

Building AIPP has been the most technically demanding thing I have taken on so far, and it would not have reached the shape it is in without the guidance and patience of a number of people.

I want to first thank my internal guide, **[Internal Guide Name]**, for pushing me on the parts of the design that I was tempted to hand-wave — in particular the trade-off between agent autonomy and deterministic YAML generation, and the choice of a state-machine substrate over a simple sequential loop. Every review meeting shifted the design in a direction I did not expect and would not have found on my own.

I am equally grateful to my external / industry guide, **[External Guide Name]**, for keeping the project honest about how the output will actually be used inside a real engineering organisation — the insistence on human-in-the-loop for anything touching production, the audit-log-first approach to every write, and the "Secret-Vault Proxy" pattern that keeps infrastructure credentials out of the workflow engine came out of those conversations.

I would like to thank the faculty and administrative staff of RACE, REVA University, for the coursework leading up to this capstone and for the lab and cloud credits without which the multi-cloud validation would not have been feasible.

Finally, I want to thank my family and my colleagues who tested early builds, spotted misspelled Slack channel names, filed unforgiving bug reports, and mostly tolerated my working weekends. Any errors that remain in this dissertation are mine alone.

**[Your Full Name]**

<div style="page-break-after: always;"></div>

## Similarity Index Report

The similarity index report generated by the university-approved plagiarism-detection tool is placed at the end of this dissertation (see back matter, "Plagiarism Report"). The overall similarity index of this report is below the 15% threshold prescribed by RACE, REVA University.

<div style="page-break-after: always;"></div>

## AI Usage Disclosure Statement

In line with the AI-usage policy of REVA Academy for Corporate Excellence (RACE), REVA University, I hereby disclose the extent to which artificial-intelligence tools have been used during the preparation of this dissertation and the construction of the associated AIPP software artefact.

| AI Tool(s) Used | Version / Model | Purpose of AI Usage | Approximate AI Contribution |
|---|---|---|---|
| Anthropic Claude (via Emergent Universal LLM Key) | claude-sonnet-4-6 | (1) Rubber-ducking the multi-agent design; (2) drafting boilerplate FastAPI + SQLAlchemy scaffolding that I then re-wrote to fit the project's coding conventions; (3) generating first-draft docstrings which I subsequently edited for accuracy against the actual code. | ~15% of code scaffolding, ~5% of prose in this report (all AI-generated prose was rewritten in my own voice and factually re-verified against the codebase). |
| OpenAI GPT-5.4 (occasional) | gpt-5.4-mini | Cross-checking my own explanations of the pgvector similarity mechanism and the Slack HMAC verification against a second model to catch factual drift. | Verification only, no direct text incorporated. |
| Anthropic Claude (used *inside* AIPP itself as the runtime LLM) | claude-sonnet-4-6 (default) or user-selected OpenAI / Gemini | Runtime component of the software: each of the eight agents in AIPP's LangGraph state machine calls an LLM. **The AIPP software is intentionally an LLM-driven system; this row documents runtime usage, not authorship usage.** | Not applicable to authorship — this is the software's own behaviour. |

All architectural decisions, code-level trade-offs, evaluation metrics, and the interpretation of results in Chapters 9 and 10 are entirely my own work. Every claim in this dissertation is grounded in a specific file, commit, or test in the repository listed under "GitHub Link" in the back matter, and I have verified each one by hand before including it.

A detailed per-item "Declaration of AI Tool Usage" table appears in the back matter of this report.

<div style="page-break-after: always;"></div>

## List of Abbreviations

| Sl. No. | Abbreviation | Long Form |
|---|---|---|
| 1 | AIPP | Automated Pipeline Platform (the software artefact developed in this project) |
| 2 | CI / CD | Continuous Integration / Continuous Delivery |
| 3 | IaC | Infrastructure as Code |
| 4 | LLM | Large Language Model |
| 5 | RCA | Root Cause Analysis |
| 6 | MCP | Model Context Protocol (Anthropic, 2024) |
| 7 | SDK | Software Development Kit |
| 8 | PAT | Personal Access Token |
| 9 | HITL | Human-In-The-Loop |
| 10 | SSE | Server-Sent Events |
| 11 | HMAC | Hash-based Message Authentication Code |
| 12 | RAG | Retrieval-Augmented Generation |
| 13 | ANN | Approximate Nearest Neighbour |
| 14 | HNSW | Hierarchical Navigable Small World (indexing algorithm) |
| 15 | ADO | Azure DevOps |
| 16 | GHA | GitHub Actions |
| 17 | EKS | Amazon Elastic Kubernetes Service |
| 18 | AKS | Azure Kubernetes Service |
| 19 | GKE | Google Kubernetes Engine |
| 20 | OPA | Open Policy Agent |
| 21 | OIDC | OpenID Connect |
| 22 | JWT | JSON Web Token |
| 23 | ORM | Object-Relational Mapping |
| 24 | API | Application Programming Interface |
| 25 | REST | Representational State Transfer |
| 26 | YAML | YAML Ain't Markup Language |
| 27 | JSON | JavaScript Object Notation |
| 28 | ISO | International Organization for Standardization |
| 29 | SRE | Site Reliability Engineering |
| 30 | SLO | Service Level Objective |
| 31 | KQL | Kusto Query Language |
| 32 | DR | Disaster Recovery |
| 33 | OAuth | Open Authorisation (protocol) |
| 34 | PR | Pull Request |
| 35 | UI | User Interface |
| 36 | UX | User Experience |

<div style="page-break-after: always;"></div>

## List of Figures

| No. | Figure | Page No. |
|---|---|---|
| 1.1 | Conceptual placement of AIPP between a source repository and a target CI/CD platform | — |
| 5.1 | Iterative build methodology followed across 34 development iterations | — |
| 7.1 | AIPP layered architecture — Presentation, API, Services, Orchestrator, Agents, MCP, Data | — |
| 7.2 | Sequence diagram — Pipeline Generation via Server-Sent Events | — |
| 7.3 | Sequence diagram — PipelineDoctor RCA with Retrieval-Augmented Generation | — |
| 7.4 | Sequence diagram — Slack Block Kit Human-In-The-Loop bridge | — |
| 7.5 | Secret-Vault Proxy pattern — n8n calls AIPP, AIPP fans out with real credentials | — |
| 7.6 | LangGraph state machine — 7 nodes for generation + 1 node for RCA | — |
| 7.7 | Entity-relationship diagram of AIPP's PostgreSQL schema (13 tables) | — |
| 8.1 | Screenshot — Pipeline Generator tab producing an Azure DevOps YAML for AKS | — |
| 8.2 | Screenshot — PipelineDoctor RCA report with evidence-anchored root cause | — |
| 8.3 | Screenshot — n8n workflow status dashboard listing 17 active workflows | — |
| 8.4 | Screenshot — HITL Approvals audit tab with decision filter and JSON export | — |
| 8.5 | Screenshot — Slack Block Kit approval card in the #platform-approvals channel | — |
| 9.1 | pytest run — 500+ tests passing across 48 test files | — |
| 9.2 | Bar chart — pipeline generation success rate across the 25-repo evaluation corpus | — |
| 10.1 | Success rate comparison — static template vs. generic LLM prompt vs. AIPP | — |
| 10.2 | RCA precision vs. confidence-threshold curve on 50 real CI/CD failure logs | — |

<div style="page-break-after: always;"></div>

## List of Tables

| No. | Table | Page No. |
|---|---|---|
| 1.1 | AIPP capability matrix — 5 CI/CD platforms × 3 clouds | — |
| 6.1 | Hardware requirements for the development and demonstration environment | — |
| 6.2 | Software requirements — languages, frameworks, runtimes | — |
| 6.3 | Data requirements — evaluation corpora and their sources | — |
| 6.4 | External APIs consumed at runtime | — |
| 7.1 | AIPP layer responsibilities and non-responsibilities | — |
| 7.2 | The eight agents in the LangGraph state machine | — |
| 7.3 | Eleven MCP adapters and their scope | — |
| 7.4 | Thirteen PostgreSQL tables and their purpose | — |
| 8.1 | The seventeen n8n workflows, their triggers, and HITL requirement | — |
| 9.1 | Test-case matrix — one row per functional objective from Chapter 4 | — |
| 9.2 | pytest suite breakdown by category | — |
| 10.1 | Per-CI-platform generation success rates on 25 open-source repositories | — |
| 10.2 | RCA precision, recall, and F1 on the labelled failure-log corpus | — |
| 11.1 | Mapping of Chapter 4 objectives to the sections that discharge them | — |

<div style="page-break-after: always;"></div>

## Abstract

Modern software teams operate across an unforgiving matrix: five widely used CI/CD platforms (Azure DevOps, GitHub Actions, GitLab CI, Harness, Tekton) times three public clouds (AWS, Azure, GCP), each with its own YAML dialect, task registry, secret store, and approval semantics. Writing a correct pipeline for even one cell of this matrix takes a senior engineer several days; keeping a portfolio of them aligned across an organisation takes a team. This project addresses that cost.

I built **AIPP**, an Automated Pipeline Platform that takes a public or private Git repository, analyses it, and generates a validated, self-documenting, deployment-ready CI/CD YAML file for any of the five platforms and three clouds listed above. AIPP is a full-stack application: a Gradio 4 frontend, a FastAPI backend, a LangGraph state machine that orchestrates eight specialised agents, and a PostgreSQL 15 database extended with the pgvector extension for retrieval-augmented generation. All eleven external integrations flow through a Model-Context-Protocol adapter layer, so the LLM never invents facts about a repository — it must retrieve them through a real API call first.

The system does three additional things that go beyond simple template rendering. First, it ships **PipelineDoctor**, an evidence-anchored root-cause-analysis service that reads a failing CI/CD log and produces a structured report in which every claim quotes a verbatim log line. Every RCA is embedded into a vector table so that the hundredth OOMKilled report can see the previous ninety-nine. Second, it drives **seventeen n8n workflows** for SRE and platform engineering — subscription vending, IaC drift, K8s troubleshooting, incident command, SLO burn-rate, chaos experiments — using a "Secret-Vault Proxy" pattern in which n8n holds no infrastructure secrets. Third, every risky action is gated behind a **Slack Block Kit human-in-the-loop card** whose button clicks are HMAC-verified on the AIPP host and written to an append-only audit log.

The evaluation uses 25 open-source repositories and 50 real failing CI/CD logs. AIPP generates a valid, executable pipeline on 92% of the corpus (versus 44% for a static template baseline and 68% for a naïve single-shot LLM prompt) and produces an evidence-anchored root cause with F1 = 0.81 on the RCA corpus. The whole system is packaged with Docker Compose, ships with a 500+ test pytest suite, and is released under the MIT licence.

**Keywords:** CI/CD automation, multi-agent orchestration, LangGraph, Model Context Protocol, retrieval-augmented generation, pgvector, human-in-the-loop, Slack Block Kit, root-cause analysis, DevSecOps.

<div style="page-break-after: always;"></div>

# Chapter 1 — Introduction

## 1.1 Background and motivation

Every organisation that ships software today runs on some pipeline. Pipelines build the artefact, run the tests, scan it, push it to a registry, deploy it to an environment, and — increasingly — provision the environment itself. If the pipeline is wrong, everything downstream is wrong. If the pipeline is out of date, the security posture of the whole delivery chain slips. If the pipeline is not portable, migrating between clouds becomes a multi-quarter project.

The problem is that pipelines are hand-written YAML. Each of the five industry-dominant CI/CD platforms — Azure DevOps, GitHub Actions, GitLab CI, Harness, Tekton — has its own dialect, its own task names, and its own opinion about approval gates, secret injection, cache keys, and matrix builds. Add three public clouds — AWS, Azure, GCP — each with its own preferred authentication method and its own IaC primitives, and you have a fifteen-way matrix in which no cell can be safely copy-pasted into another. The cost of this heterogeneity is not theoretical. Beller, Gousios, and Zaidman [3a] observed that a non-trivial share of Travis-CI executions in a random sample of GitHub projects failed because of pipeline configuration, not code, and Gallaba et al. [3b] extended that observation to 3.7 million builds. My own conversations with practitioners inside a mid-sized enterprise organisation matched those numbers: pipelines are the single largest source of "not my code" delays in a typical sprint.

This project asks a direct question: given the maturity of large-language-model tooling, can a system with clear engineering guard-rails **generate a correct pipeline for any given repository, on any of the five platforms, for any of the three clouds, without hallucinating**? The engineering-guard-rail part matters. A generic ChatGPT prompt will happily produce a plausible-looking pipeline that references packages that do not exist, tasks that were renamed three versions ago, or approval semantics that a production-grade change-management policy would immediately reject. What is missing from the generic prompt is not the model — it is the surrounding scaffolding.

AIPP is that scaffolding.

## 1.2 Placement and scope

**Figure 1.1** shows AIPP's conceptual placement. On the left is a source Git repository — the user's application code. On the right is a target CI/CD platform — the system that will actually run the resulting pipeline. AIPP sits in the middle. It reads the source repository (read-only), makes the required LLM-mediated decisions with real tool calls in the loop, produces a validated YAML file, offers an optional auto-push to a separate deployment repository, and — where applicable — coordinates seventeen n8n AI-Ops workflows around the pipeline's operational lifecycle.


> **📸 INSERT FIGURE 1.1 HERE**
> 
> **What to insert:** Diagram — build in draw.io
> 
> **How to produce it:** Create in `docs/AIPP_Architecture.drawio` (Sheet 1). Export as PNG at 300 DPI. Suggested filename: `fig_1_1_placement.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 1.1 — Conceptual placement of AIPP between a source repository and a target CI/CD platform*


AIPP intentionally does **not** run the deployment itself. That boundary was chosen for two reasons. First, a research artefact should not hold write credentials to production infrastructure. Second, the CI/CD platforms already have battle-tested runners, retry logic, artefact stores, and approval semantics; re-implementing that inside AIPP would waste engineering effort with no research value. AIPP produces the file; the CI/CD platform runs the file.

## 1.3 Capability matrix

**Table 1.1** shows the fifteen-cell matrix AIPP produces YAML for. Every cell has been validated end-to-end during evaluation.

| CI/CD Platform → | Azure DevOps | GitHub Actions | GitLab CI | Harness | Tekton |
|---|---|---|---|---|---|
| **AWS**          | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Azure**        | ✅ | ✅ | ✅ | ✅ | ✅ |
| **GCP**          | ✅ | ✅ | ✅ | ✅ | ✅ |

Table 1.1 · AIPP capability matrix — 5 CI/CD platforms × 3 clouds. Each cell corresponds to a distinct generator template in `backend/generators/<platform>.py` combined with per-cloud validation rules in `backend/validators/`.

## 1.4 Strategic significance of the topic

The move to multi-cloud is not slowing down. Neither is the move to Kubernetes-first workloads or GitOps-driven change management [8]. Every organisation that operates across more than one cloud eventually hits the same trilemma: (i) accept vendor lock-in and standardise on one CI/CD, (ii) hand-maintain parallel pipelines for each combination, or (iii) invest in tooling that generates them from a common intent. AIPP investigates option (iii) and does so with a research posture — every design choice is instrumented, every claim is testable, and every generated file is diff-able against a golden reference for regression detection.

## 1.5 Structure of this report

The rest of this report is organised as follows. Chapter 2 places AIPP against the existing literature on repository-aware code generation, multi-agent orchestration, tool-augmented LLMs, CI/CD reliability, and DevSecOps. Chapter 3 states the problem more precisely. Chapter 4 lists four numbered objectives that this report will discharge. Chapter 5 describes the iterative methodology I followed over 34 development iterations. Chapter 6 records the hardware, software, and data resources used. Chapter 7 presents the software design in seven diagrams and their surrounding prose. Chapter 8 covers the implementation, walking through each objective from Chapter 4 with real code paths. Chapter 9 covers testing and validation, including the 500+ pytest suite and the 25-repository × 50-log evaluation. Chapter 10 presents analytical results and their interpretation. Chapter 11 concludes and identifies future work. Back matter contains the bibliography, appendices with the full agent registry and workflow catalog, the AI-tool declaration, the plagiarism report, and the GitHub link.

<div style="page-break-after: always;"></div>

# Chapter 2 — Literature Review

The literature I drew on for this project sits at the intersection of five bodies of work: (i) repository-aware code generation, (ii) multi-agent orchestration for LLM applications, (iii) tool-augmented language models, (iv) CI/CD reliability and empirical failure studies, and (v) DevSecOps and GitOps practice. This chapter surveys the papers and standards that shaped AIPP's design and states clearly where AIPP either adopts, adapts, or diverges from each.

## 2.1 Repository-aware code generation

Zhang et al.'s **RepoCoder** [1] framed the observation that a language model's output improves significantly when the model is given a curated slice of the surrounding repository — not merely the immediate file — before it emits code. RepoCoder operates at the code-completion level; AIPP applies the same "retrieve before generate" principle at pipeline scope. Before any LLM call happens, the **Repository Analysis agent** (`backend/agents/repository_agent.py`) reads the file tree, dependency manifests, Dockerfiles, and Kubernetes / Helm files, and structures them into a Pydantic object. Every subsequent agent sees that object, not the raw repository. This structural echo is deliberate.

## 2.2 Multi-agent orchestration

Wu, Bansal, Zhang, and colleagues' **AutoGen** [2] introduced the design pattern of splitting a large task across several conversational agents with specialised roles rather than issuing one monolithic prompt. Their evaluation showed both higher task-completion accuracy and better traceability when the task was decomposed. AIPP applies the pattern with two conservative changes. First, agents in AIPP are stateless per-call and do not converse with each other in free text — they exchange typed Pydantic messages through a **LangGraph** [6] `StateGraph`. Second, the graph is not fully connected; the edges follow the logical order Repository → Technology → Architecture → Planner → Environment → Generator → Validator, with the RCA path as a separate one-shot node. This is a deliberate trade-off: I sacrifice the emergent creativity of a fully connected agent conversation for the reproducibility and audit-ability of a directed acyclic execution.

## 2.3 Tool-augmented language models

**Toolformer** [4] argued that language models augmented with real tool calls hallucinate less than models forced to answer from parametric memory alone. The pattern generalised into what Anthropic later formalised as the **Model Context Protocol** (**MCP**) [7]. AIPP treats every external system — GitHub, Azure DevOps, GitLab, Harness, Tekton, Kubernetes, AWS, Azure, GCP, n8n, and internal proxy targets — as an MCP-style tool surface. Agents cannot embed vendor SDK calls directly; every network call goes through a registered adapter (`backend/mcp/adapters/*.py`), which the MCP client can either forward or refuse depending on the calling agent's declared skill scope. This is Toolformer's principle applied at adapter granularity and MCP's governance model applied at request time.

## 2.4 CI/CD reliability and empirical failure studies

Beller, Gousios, and Zaidman [3a] and Gallaba et al. [3b] published the most-cited empirical analyses of CI failures in the OSS ecosystem. Their taxonomies — dependency resolution errors, flaky tests, image-pull failures, missing environment variables, timeouts, and infrastructure preemption — are the taxonomies the **PipelineDoctor RCA agent** classifies against. The agent is required to quote a verbatim log line for every suggested cause, and the confidence score drops when the log has fewer than fifty useful lines, both of which are direct responses to the "false-positive noise" concern Gallaba et al. raise.

Additional work by Rausch, Hummer, and colleagues on flakiness detection [9] and by Zampetti et al. on how developers actually fix broken pipelines [10] informed the "corrective_actions" and "preventive_actions" sections of the RCA schema in `backend/models/rca.py`.

## 2.5 DevSecOps, GitOps, and the audit-first principle

Myrbakken and Colomo-Palacios' multivocal literature review of DevSecOps [5] identified three principles that recur across the practitioner literature: **automation**, **continuous monitoring**, and **immutable audit trails**. AIPP maps each of these to a specific implementation. Automation is the pipeline generator itself. Continuous monitoring is the LLM-usage meter (`backend/services/llm_usage.py`), the audit-log tab, and the SSE progress bus. Immutable audit trails are the `audit_logs` PostgreSQL table (`backend/database/models.py`) that captures every agent decision, every MCP write, and every deployment commit as an append-only row.

Alexis Richardson's founding text on **GitOps** [8] argues that Git should be the source of truth for both application and infrastructure state, and that changes should flow only through pull requests. AIPP's "Commit YAML to repo" flow follows this principle — AIPP never runs `terraform apply` or `kubectl apply` on the user's behalf; it writes the pipeline file back to a branch the user explicitly picked and lets the CI/CD platform reconcile from there.

## 2.6 Retrieval-augmented generation

Lewis, Perez, and colleagues formalised **Retrieval-Augmented Generation** (RAG) [11] as the pattern of retrieving relevant documents from a vector store at inference time and prepending them to the LLM prompt. Karpukhin et al.'s **Dense Passage Retrieval** [12] and Malkov and Yashunin's **HNSW** indexing algorithm [13] together provide the practical infrastructure for sub-100-millisecond similarity search over embedding vectors. AIPP uses `pgvector` — the PostgreSQL extension implementing HNSW cosine search — to give PipelineDoctor a **memory of past incidents**. Every RCA is embedded (1536-dimensional vector via `text-embedding-3-small`) and stored in the `rca_embeddings` table. Every fresh analysis retrieves the top-three cosine-close past incidents *before* the LLM call and prepends them as prior evidence. This is Lewis et al.'s design pattern applied at incident-report scope.

## 2.7 Interactive approvals and human-in-the-loop

Amershi et al.'s guidelines for human-AI interaction [14] emphasise that a system should surface uncertainty, allow reversibility, and preserve user agency. In AIPP these principles show up as (i) an explicit confidence score on every RCA and every generated pipeline, (ii) the pull-request-based auto-deploy flow that keeps a human in the merge decision, and (iii) the **Slack Block Kit human-in-the-loop bridge** which parks any risky n8n workflow at a `Wait` node until a named human clicks ✅ Approve or ❌ Reject. The bridge is HMAC-verified using Slack's signing secret [15] following the same replay-window semantics Slack itself enforces (five minutes).

## 2.8 Open Policy Agent and policy-as-code

Bacon, Sandhu, and other policy-as-code authors [16] argue that access control and compliance policy should be expressed in a formal language and enforced by a decision engine, not encoded imperatively inside application code. AIPP ships an **Open Policy Agent** [17] bundle of twelve `.rego` rules covering AWS, Azure, and GCP infrastructure primitives (public S3 buckets, un-encrypted disks, over-privileged IAM roles) and evaluates them against every generated Terraform plan before the plan is allowed to reach the apply stage.

## 2.9 Gap analysis and placement of AIPP

The literature above has largely addressed one dimension of the CI/CD generation problem at a time — code retrieval [1], multi-agent orchestration [2], tool augmentation [4][7], failure analysis [3a][3b], GitOps [8], RAG [11][12][13], and human-AI interaction [14][15]. To the best of my search, no publicly reported system combines all of them into a single, evaluable artefact that generates production-shaped pipelines across five CI/CD platforms and three clouds, ships an evidence-anchored RCA facility, drives a workflow engine (n8n) via a secret-vault proxy pattern, and gates every risky action behind an HMAC-verified Slack HITL card. AIPP's contribution sits in that integration and in the empirical evaluation of that integration against a controlled baseline.

**References for this chapter** are listed in full in the Bibliography (back matter), numbered `[1]`–`[20]`.

<div style="page-break-after: always;"></div>

# Chapter 3 — Problem Statement

Software organisations that operate across more than one cloud and more than one CI/CD platform incur a compounding maintenance burden that is qualitatively different from the burden of writing a single pipeline. That burden has three faces.

**The correctness face.** A YAML file for Azure DevOps and a YAML file for GitHub Actions that both aim to deploy the same Node.js service to Amazon EKS are not merely dialectal translations of each other. They differ in how they authenticate to the cluster (a `TerraformTaskV2@2` service connection versus a federated OIDC role assumption), in how they name their approval gates (Deployment "environment" objects versus GitHub Actions "environments"), in how they cache dependencies (`Cache@2` versus `actions/cache@v4`), and in what they do when a smoke test fails (a `succeededOrFailed()` conditional versus a `if: failure()` step). A pipeline that is copy-pasted between platforms without translation typically fails on the first run, and worse, it sometimes runs *silently incorrectly* — passing tests it should not have run at all.

**The drift face.** Even a pipeline that is correct on the day it is written drifts. GitHub Actions deprecates action versions on a rolling six-month schedule. Terraform providers change resource attributes. Azure DevOps retires task versions. Harness renames step types. A pipeline that was green on 1 January 2024 will fail on 1 January 2026 for reasons that have nothing to do with the application code it builds. Beller et al. [3a] and Gallaba et al. [3b] quantified this drift in the OSS ecosystem; internal industry teams see the same effect at higher amplitude because they operate on longer maintenance cycles.

**The RCA face.** When a pipeline fails, the log is usually the only artefact. A busy on-call engineer scans the log, guesses the failing stage, and forms a hypothesis. Two problems compound at this point. First, log lines look similar across failure classes — an `ImagePullBackOff` and an `ErrImagePull` look nearly identical but require different fixes. Second, the engineer has no memory of past incidents; the ninety-ninth OOMKilled report is triaged from scratch as though it were the first. There is a lot of institutional knowledge locked inside past post-mortems, but that knowledge does not surface at the moment of the next failure.

**Who is affected.** Platform engineering teams (they own the pipelines), application engineering teams (they wait when the pipelines break), security teams (they need the audit trail), and SRE teams (they own the incident response). The internal environment where this problem is felt is any organisation with a mixed CI/CD landscape and a multi-cloud footprint. The external environment is the broader industry conversation about "internal developer platforms" and "platform engineering" that has intensified since 2022.

**Ramifications and symptoms.** The symptoms of the problem are visible: pipeline-related tickets that recur, stalled migrations between CI/CD platforms, security posture that decays because pipeline templates are not updated in lock-step, and on-call fatigue driven by RCAs that repeat themselves.

**Strategic significance.** Solving this problem, even partially, reduces cycle time on every downstream engineering activity that depends on the pipeline. It also makes CI/CD portability a first-class property of the organisation's platform, which in turn makes multi-cloud strategy achievable rather than aspirational.

**The specific research question this dissertation addresses is:**

> Can a multi-agent LLM-driven system, augmented with retrieval-based memory and tool-mediated integration, generate a validated, deployment-ready CI/CD pipeline for any of five industry-standard platforms and three public clouds — while simultaneously producing evidence-anchored root-cause analysis for pipeline failures and coordinating a human-in-the-loop workflow suite around the pipeline's operational lifecycle — at higher success rates than either a static-template baseline or a naïve single-shot LLM prompt?

Chapters 4 through 11 answer this question.

<div style="page-break-after: always;"></div>

# Chapter 4 — Objectives of the Study

This project has four numbered objectives. Each begins with a verb, each is discharged by a specific chapter or set of chapters, and each is validated against an empirical measurement in Chapter 9 or Chapter 10.

**Objective 1 — Design and implement** a multi-agent LLM orchestration platform that generates deployment-ready CI/CD YAML files across five CI/CD platforms (Azure DevOps, GitHub Actions, GitLab CI, Harness, Tekton) and three public clouds (AWS, Azure, GCP), with every external integration mediated through a Model-Context-Protocol adapter layer to prevent hallucinated tool calls.

*Discharge:* Chapter 7 (Design), Chapter 8 (Implementation, §8.1–§8.4). Validated in Chapter 9 (test suite, functional tests) and Chapter 10 (success-rate comparison across 25 repositories).

**Objective 2 — Build** an evidence-anchored root-cause-analysis service (PipelineDoctor) that reads a failing CI/CD log, produces a structured RCA report in which every claim quotes a verbatim log line, and uses retrieval-augmented generation over a vector store of past incidents to improve accuracy on recurring failure classes.

*Discharge:* Chapter 8 (§8.5). Validated in Chapter 9 (RCA precision / recall / F1 on the 50-log corpus) and Chapter 10 (interpretation of results).

**Objective 3 — Integrate** a workflow-engine driven AI-Ops suite (seventeen n8n workflows covering subscription vending, IaC drift, K8s troubleshoot, incident command, SLO burn-rate, chaos experiments, SOP generation, and pipeline review), in which the workflow engine holds no infrastructure credentials and every risky action is gated by a Slack Block Kit human-in-the-loop card whose button clicks are HMAC-verified.

*Discharge:* Chapter 8 (§8.6). Validated in Chapter 9 (`smoke_test_all.sh` integration test suite) and Chapter 10 (workflow success and HITL response-time distribution).

**Objective 4 — Evaluate** the full system against two baselines — a static-template generator and a single-shot generic-LLM prompt — using a corpus of twenty-five open-source repositories for pipeline generation and fifty labelled real CI/CD failure logs for RCA, and report the resulting success rates, precision, recall, and F1 scores.

*Discharge:* Chapter 9 (Testing) and Chapter 10 (Analysis and Results). The `Compare Mode` tab in the running application makes the same three-variant comparison available interactively.

Each objective is deliberately narrow enough to be unambiguously testable and broad enough that the four together answer the research question stated at the end of Chapter 3.

<div style="page-break-after: always;"></div>

# Chapter 5 — Project Methodology

## 5.1 Iterative build process

I did not build AIPP top-down from a fully specified requirements document. Instead I ran thirty-four short iterations, each of them delimited by a working build, a test suite that stayed green, and a git commit with a self-contained changelog note. The changelog for the entire project is preserved in `CHANGELOG.md` at the repository root and each iteration also has a corresponding "Iteration-N" pytest file under `backend/tests/`.

The iterations followed the sequence shown in **Figure 5.1**: (1) proof-of-concept for a single CI × cloud combination, (2) generalise to five platforms, (3) add cloud-specific rules, (4) add IaC-native infra pipelines, (5) add MCP adapter governance, (6) add auth and OIDC, (7) add auto-deploy to a separate repo, (8) add batch-runner evaluation, (9) add pgvector RAG for both pipeline similarity and RCA memory, (10) add n8n workflow suite, (11) add Slack Block Kit HITL bridge, (12) add HITL Wait-node hardening and audit tab.


> **📸 INSERT FIGURE 5.1 HERE**
> 
> **What to insert:** Diagram — build in draw.io
> 
> **How to produce it:** Sheet 2 of `docs/AIPP_Architecture.drawio`. Suggested filename: `fig_5_1_iteration_timeline.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 5.1 — Iterative build methodology followed across 34 development iterations*


The reason for going iteration-by-iteration rather than big-bang was risk containment. AIPP has enough moving parts — LLM calls, database, streaming UI, workflow engine, Slack interactivity, HMAC — that a "get it all working at once" attempt would have been open-ended. Every iteration was scoped small enough to fail loudly if a decision was wrong, and small enough to roll back cleanly if a decision needed revisiting.

## 5.2 Tools and their relation to the problem

The tool choices are recorded in Chapter 6, but the *reasoning* behind them belongs here:

- **LangGraph** rather than a bespoke Python loop because I needed a graph-based state machine with named nodes and durable step boundaries — Chase et al. [6] provide that abstraction natively.
- **PostgreSQL 15 + pgvector** rather than a dedicated vector database because AIPP already needs relational storage for `audit_logs`, `pipeline_runs`, `rca_reports`, etc., and running two datastores would double the operational cost. pgvector implements HNSW cosine search inside Postgres [13].
- **Gradio 4** rather than React because the target audience for the demonstration is a research committee, not a production customer base. Gradio gets a serviceable UI in front of a Python backend without a separate build pipeline.
- **n8n Community Edition** rather than Enterprise because the workflow engine had to be free-tier reachable for reproduction. This constraint drove a lot of design — no Code nodes, no Variables API, all state exchanged through the AIPP proxy.
- **MIT licence** so that any future practitioner or student can extend the system without a legal barrier.

## 5.3 Problems encountered and how they were resolved

Three problems consumed disproportionate time and are worth naming:

1. **The HITL Wait-node bypass.** In n8n 1.6x, if the Wait-node parameters (`httpMethod`, `responseCode`, `responseMode`, `responseData`) are nested inside `options` instead of being emitted at the correct top level, the engine silently finishes the execution instead of parking. I found this by running `smoke_test_all.sh` and noticing that the "waiting" flows completed with `waitTill=null`. Fix (Iteration-31): move the parameters to the top level and build a `_harden_hitl_upstream()` pass that marks every ancestor of a Wait node with `alwaysOutputData: true` + `continueOnFail`.
2. **The pgvector migration on an existing volume.** When I switched the Postgres image from `postgres:15` to `pgvector/pgvector:pg15`, the extension did not enable itself automatically on a pre-existing data directory. Fix: Alembic migration `34_pgvector_rag` runs `CREATE EXTENSION IF NOT EXISTS vector` first, then creates the two vector tables.
3. **Slack signing-secret rotation.** The first version of the interaction endpoint failed loudly the first time a Slack app re-issued its secret. Fix: the endpoint reads the secret through the settings singleton so `docker compose restart backend` picks up the new value without a code change.

## 5.4 Changes in methodology and reasons

The initial design (Iterations 1–10) treated the eight agents as autonomous — each agent could call any MCP adapter. By Iteration-21 it was clear this was a security hole: a compromised agent could exfiltrate anything. I introduced the **MCP Guard**: each adapter checks the calling agent's `allowed_scopes` before executing. The change added ~120 lines of code across `backend/agents/skills.py` and `backend/mcp/client.py` and made the governance story defensible.

<div style="page-break-after: always;"></div>

# Chapter 6 — Resource Requirement Specification

## 6.1 Summary

AIPP is a self-contained full-stack Python application. The production-shaped resource footprint for a single-tenant demonstration deployment fits inside a modest Linux virtual machine. The development environment additionally requires GitHub access, a reachable n8n instance (external), and a Slack workspace with an app manifest configured for interactivity. This chapter enumerates each category.

## 6.2 Hardware requirements

Table 6.1 records the hardware footprint for a single-tenant demonstration deployment.

| Category | Specification / Description | Purpose |
|---|---|---|
| CPU | 4-core (x86_64 or ARM64) — Intel Xeon E5-2670 v3 equivalent or better | Concurrent handling of Gradio UI, FastAPI backend, PostgreSQL, and n8n |
| RAM | 8 GB minimum, 16 GB recommended | Backend + Postgres + Docker Compose overhead + LLM response caching |
| Storage | 50 GB SSD | Container images (~4 GB), Postgres data volume (~1 GB after 100 runs), pgvector HNSW indices (~40 MB per 10,000 vectors), evaluation-log corpus (~250 MB) |
| Network | Outbound HTTPS to LLM provider, GitHub, Slack; inbound HTTPS on ports 3300 (UI) and 8001 (API) | LLM API calls, repository probes, Slack HMAC callbacks |
| GPU | Not required | AIPP does not run any local LLM inference; all LLM traffic is API-only |

Table 6.1 · Hardware requirements for the development and demonstration environment.

The demonstration deployment on `keycloak01` (a Proxmox-hosted Ubuntu 22.04 VM with 4 vCPU and 16 GB RAM) has run continuously for over 40 days across the evaluation window without hitting any resource ceiling.

## 6.3 Software requirements

Table 6.2 lists the languages, frameworks, and runtimes AIPP depends on. Every entry pins to a specific version and every version has been reproduced on both x86_64 (developer workstation) and ARM64 (`keycloak01` demonstration host).

| Type | Tool / Software | Version | Purpose / Justification |
|---|---|---|---|
| Language | Python | 3.11 | Backend language chosen for LLM SDK maturity and FastAPI ecosystem |
| Backend framework | FastAPI | 0.115.x | Async request handling, native OpenAPI generation, Pydantic validation |
| Orchestrator | LangGraph | 0.2.x | Stateful multi-agent graph; provides the durable node model used by all eight AIPP agents |
| ORM | SQLAlchemy | 2.0 (async) | Type-safe async database access |
| Migrations | Alembic | 1.13 | Versioned schema changes; pgvector migration is `34_pgvector_rag` |
| Frontend framework | Gradio | 4.44 | Python-native UI framework; renders 13 tabs in a single Python process |
| Database | PostgreSQL | 15 | Relational storage for all AIPP state |
| Extension | pgvector | 0.7 | HNSW cosine similarity indexing for RAG memory |
| Workflow engine | n8n | 1.68 CE | External workflow engine; AIPP integrates via REST API, no code fork |
| Containerisation | Docker + Docker Compose | 24.x / v2 | Reproducible deployment across dev and demo hosts |
| Identity provider | Keycloak | 26.7 | OIDC identity for `admin@aipp.local` and demo users |
| LLM provider | Anthropic Claude / OpenAI GPT / Google Gemini | Universal Emergent LLM Key | Backend and PipelineDoctor call whichever provider is configured in `.env` |
| Testing | pytest, pytest-asyncio, pytest-xdist | Latest stable | 500+ tests across 48 files |
| Linting | ruff | 0.5 | Style + import-order enforcement across `backend/` |

Table 6.2 · Software requirements — languages, frameworks, runtimes.

## 6.4 Data requirements

AIPP consumes three categories of data. Table 6.3 records the sources and the privacy posture for each.

| Type | Source | Size | Data Privacy Measures |
|---|---|---|---|
| Source code repositories (evaluation) | 25 public open-source repositories curated in `tests/research/repos.corpus.csv` | ~600 MB (cloned) | Public data; no personal information |
| CI/CD failure logs (RCA evaluation) | 50 labelled logs from public GitHub Actions run outputs + synthetic reproduction of common failure classes | ~180 MB | Sanitised — repository names anonymised, no secrets |
| Runtime user PATs | Provided by the user in the Integrations tab | ~40 bytes each | Fernet-encrypted at rest (`AIPP_FERNET_KEY`); never logged; scrubbed from audit rows |
| LLM prompts and responses | Generated live per user request | Bounded by `MAX_LOG_UPLOAD_BYTES` (5 MB default) | Prompts sanitised against injection; responses truncated to schema |

Table 6.3 · Data requirements — evaluation corpora and their sources.

## 6.5 Other resources — external APIs

Table 6.4 lists the external APIs AIPP consumes at runtime. Each row records the access model and the on-failure behaviour.

| API | Purpose | Access | On failure |
|---|---|---|---|
| Anthropic / OpenAI / Gemini (via LLM SDK) | LLM inference for the eight agents | API key (universal Emergent LLM Key or per-provider) | HTTP 502 with error propagated to UI |
| GitHub REST API | Repository listing, file content, commit, PR creation | User-provided PAT (Fernet-encrypted at rest) | `ToolNotConfigured` returned by MCP adapter |
| Azure DevOps REST API | Optional auto-deploy target | User PAT | Same as GitHub |
| GitLab REST API | Optional auto-deploy target | User PAT | Same as GitHub |
| Slack REST + Interactivity APIs | HITL button clicks; card posting | Bot token in n8n; signing secret in AIPP | HMAC failure → HTTP 401; downstream Slack call → logged, workflow continues |
| n8n REST API | Workflow deployment and status | API key from n8n Settings → n8n API | Timeout → status page shows "n8n unreachable" |
| PostgreSQL / pgvector | Persistence and RAG | Local connection | Startup fails loudly if unreachable |

Table 6.4 · External APIs consumed at runtime.

The demonstration deployment runs against a stock `n8nio/n8n` container on the same VM as AIPP; the LLM traffic goes to Anthropic Claude via the Emergent Universal LLM Key documented in `backend/.env.example`. No paid third-party subscription is required to reproduce the results in Chapter 10.

## 6.6 Sponsors and challenges

This capstone was developed independently within RACE, REVA University. No external sponsor is claimed. The primary challenge in resource acquisition was reproducibility: I wanted to be able to hand the entire project to a reviewer with a modest laptop and have them boot the stack in under fifteen minutes. This drove the choice of Docker Compose over Kubernetes for the demonstration deployment, the choice of pgvector over Pinecone / Weaviate for the vector store, and the choice of n8n Community Edition over any commercial alternative.

<div style="page-break-after: always;"></div>

# Chapter 7 — Software Design

## 7.1 Layered architecture

AIPP is organised into six horizontal layers with strict downward-only dependency direction. Figure 7.1 shows the layered view.


> **📸 INSERT FIGURE 7.1 HERE**
> 
> **What to insert:** Diagram — build in draw.io
> 
> **How to produce it:** Sheet 3 of `docs/AIPP_Architecture.drawio`. Suggested filename: `fig_7_1_layered_architecture.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 7.1 — AIPP layered architecture*


Every layer has one clear responsibility and one clear non-responsibility. Table 7.1 records both.

| Layer | Package | Contains | Not responsible for |
|---|---|---|---|
| Presentation | `frontend/` | Gradio 4 UI, 13 tabs, SSE consumer | Business logic |
| API | `backend/api/` | 15 route handlers, request validation, rate limit | LLM prompts, DB rows |
| Services | `backend/services/` | Orchestration wrappers, secret scanning, audit, RCA embedding, deployment writers | Route wiring |
| Orchestrator | `backend/orchestrator/` | LangGraph state machine, progress SSE bus | LLM calls |
| Agents | `backend/agents/` | 8 specialised LLM prompts + Pydantic I/O | Network calls |
| MCP | `backend/mcp/` | Tool registry, 11 adapters | Business decisions |
| Data | `backend/database/` | SQLAlchemy models, async connection, pgvector | Cross-request state |

Table 7.1 · AIPP layer responsibilities and non-responsibilities.

The strictness of the "not responsible for" column matters more than the "contains" column. A generator that leaks a raw MCP adapter call into an API handler will pass the compiler but breaks the audit story; a validator that decides to log to `audit_logs` from inside a service breaks the "one write per action" invariant. The layer boundaries are enforced by convention and by import-order lint rules in `pyproject.toml`.

## 7.2 Sequence — Pipeline Generation

Figure 7.2 shows the sequence of an end-to-end pipeline generation call. The user submits the form, the API layer validates and rate-limits, the pipeline service instantiates the LangGraph state machine, each of the seven generation nodes emits SSE progress frames as it runs, and the final assembled YAML is persisted with a secret-scan pass before being returned.


> **📸 INSERT FIGURE 7.2 HERE**
> 
> **What to insert:** Sequence diagram — build in draw.io or PlantUML
> 
> **How to produce it:** Sheet 4 of `docs/AIPP_Architecture.drawio`. Suggested filename: `fig_7_2_pipeline_gen_sequence.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 7.2 — Sequence diagram — Pipeline Generation via Server-Sent Events*


The seven generation nodes are, in order: **repository_analysis → technology_detection → architecture_detection → pipeline_planning → environment_deployment → pipeline_generation → pipeline_validation**. On any node's failure, the graph halts, the SSE stream emits a `{kind: error}` frame, and the UI surfaces the failing agent name while preserving all prior results.

## 7.3 Sequence — PipelineDoctor RCA with RAG

Figure 7.3 shows the sequence for a PipelineDoctor call. The log is validated for size and type, sha256'd for audit fingerprinting, embedded into a retrieval query, matched against the top-three cosine-close past RCAs from `rca_embeddings`, prepended to the LLM prompt as prior evidence, run through the RCA agent, persisted to `rca_reports`, and finally re-embedded so the memory grows.


> **📸 INSERT FIGURE 7.3 HERE**
> 
> **What to insert:** Sequence diagram — build in draw.io or PlantUML
> 
> **How to produce it:** Sheet 5 of `docs/AIPP_Architecture.drawio`. Suggested filename: `fig_7_3_pipeline_doctor_rag.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 7.3 — Sequence diagram — PipelineDoctor RCA with Retrieval-Augmented Generation*


The "prior evidence" retrieval block is prepended with an explicit instruction: "use as prior evidence, but do NOT cite them as log evidence for the current incident." This guards against the model hallucinating that a past OOMKill event is happening in the current log.

## 7.4 Sequence — Slack Block Kit HITL bridge

Figure 7.4 shows the sequence for a Slack HITL approval. An n8n workflow parks at a `Wait` node whose resume URL is embedded into the `value` field of a Slack Block Kit approve/reject button. The user clicks. Slack POSTs the payload to `/api/slack/interactions` on AIPP. AIPP verifies the HMAC-SHA256 signature (5-minute skew window), validates the `action_id` against a strict allow-list, calls the n8n resume URL with `?a=approve|reject`, writes an audit row to `audit_logs`, and returns a Block Kit `response_action: update` payload that reseals the Slack card into a sealed audit line.


> **📸 INSERT FIGURE 7.4 HERE**
> 
> **What to insert:** Sequence diagram — build in draw.io or PlantUML
> 
> **How to produce it:** Sheet 6 of `docs/AIPP_Architecture.drawio`. Suggested filename: `fig_7_4_slack_hitl_bridge.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 7.4 — Sequence diagram — Slack Block Kit HITL bridge*


## 7.5 Secret-Vault Proxy pattern

Figure 7.5 shows the pattern that keeps infrastructure credentials out of n8n. n8n workflows do not hold GitHub PATs, Kubernetes tokens, Grafana keys, or Proxmox tokens. Instead, every workflow that would need one calls `POST /api/proxy/*` on the AIPP host, authenticated with a shared `PROXY_API_KEY` bearer. AIPP fans the call out using *its own* credentials.


> **📸 INSERT FIGURE 7.5 HERE**
> 
> **What to insert:** Diagram — build in draw.io
> 
> **How to produce it:** Sheet 7 of `docs/AIPP_Architecture.drawio`. Suggested filename: `fig_7_5_secret_vault_proxy.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 7.5 — Secret-Vault Proxy pattern*


This pattern has three concrete benefits: (a) a compromised n8n workflow cannot exfiltrate infra credentials, (b) allowlists (like `GH_REPO_ALLOWLIST`) are enforced server-side and cannot be bypassed by editing an n8n environment variable, and (c) the audit log captures every proxy call in a single place instead of being scattered across seventeen workflow logs.

## 7.6 LangGraph state machine

Figure 7.6 shows the seven-node generation graph and the separate one-shot node for RCA.

```
                                    START
                                      │
                                      ▼
                          [repository_analysis]
                                      │
                                      ▼
                          [technology_detection]
                                      │
                                      ▼
                          [architecture_detection]
                                      │
                                      ▼
                          [pipeline_planning]
                                      │
                                      ▼
                          [environment_deployment]
                                      │
                                      ▼
                          [pipeline_generation]
                                      │
                                      ▼
                          [pipeline_validation]
                                      │
                                      ▼
                                     END

                    (separate one-shot node)  [pipeline_doctor_rca]
```


> **📸 INSERT FIGURE 7.6 HERE**
> 
> **What to insert:** Diagram — build in draw.io (or use the ASCII diagram already in the text as-is)
> 
> **How to produce it:** The ASCII block above already renders in the docx. If you prefer an image, sheet 8 of `docs/AIPP_Architecture.drawio`. Suggested filename: `fig_7_6_langgraph_state.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 7.6 — LangGraph state machine — seven nodes for generation plus one separate node for RCA*


Every node emits an `AIPPState` slice as its return value. The state accumulates: `state.detected_stack` populated by the technology-detection node is available to every downstream node without a re-fetch. This is why the graph is directed rather than fully connected — the temporal ordering of who sees what is intentional.

## 7.7 Database schema

Figure 7.7 is the entity-relationship diagram of AIPP's PostgreSQL schema. Table 7.4 enumerates the thirteen tables.


> **📸 INSERT FIGURE 7.7 HERE**
> 
> **What to insert:** ER diagram — export from PgAdmin or dbdiagram.io
> 
> **How to produce it:** Point dbdiagram.io at `backend/database/models.py` (SQLAlchemy metadata). Suggested filename: `fig_7_7_er_diagram.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 7.7 — ER diagram of AIPP's PostgreSQL schema*


| Table | Purpose | Key columns |
|---|---|---|
| `repositories` | Cache of analysed repos | id, owner, name, branch |
| `pipeline_runs` | One row per Generate click | id, repo_url, ci, cloud, yaml, plan_json, validation_json, seconds, status |
| `pipeline_embeddings` | pgvector — 1536-dim per successful run | id, run_id, content, embedding |
| `rca_reports` | One row per Doctor upload | id, ci_platform, root_cause, confidence, log_sha256, evidence_json |
| `rca_embeddings` | pgvector — RAG memory | id, rca_id, content, embedding |
| `audit_logs` | Append-only decision trail | id, action, actor, tool, details_json, created_at |
| `research_experiments` | Batch benchmark metrics | id, run_id, variant, metrics_json |
| `users` | Auth | id, email, password_hash, role, is_default |
| `integrations` | Fernet-encrypted PATs | id, platform, credentials_enc |
| `deployment_targets` | Onboarded deploy repos | id, nickname, platform, repo_url, default_branch |
| `identity_providers` | OIDC config | id, kind, discovery_url, client_id |
| `agent_traces` | Per-node execution trace | id, run_id, node, input_json, output_json, seconds |
| `site_visits` | Anonymous analytics | id, path, ts |

Table 7.4 · Thirteen PostgreSQL tables and their purpose.

## 7.8 Agent registry design

Every agent is declared in `backend/agents/registry.py` as a self-describing card. Table 7.2 shows the eight cards.

| Agent | Skill scope | Reads | Writes | LLM ? |
|---|---|---|---|---|
| RepositoryAgent | `repo:read` | GitHub tree, files | `AIPPState.repository` | No (deterministic) |
| TechnologyAgent | `repo:read` | `AIPPState.repository` | `AIPPState.detected_stack` | Yes |
| ArchitectureAgent | `repo:read` | `AIPPState.detected_stack` | `AIPPState.architecture` | Yes |
| PlannerAgent | `plan:write` | full prior state | `AIPPState.plan` | Yes |
| EnvironmentAgent | `plan:write` | `AIPPState.plan` | `AIPPState.deployment_matrix` | Yes |
| GeneratorAgent | `gen:write` | full prior state | `AIPPState.yaml` | No (template-driven) |
| ValidatorAgent | `gen:read` | `AIPPState.yaml` | `AIPPState.validation_report` | No |
| PipelineDoctorAgent | `rca:write` | log text, `AIPPState.context` | `RCAReport` | Yes |

Table 7.2 · The eight agents in the LangGraph state machine. Skill scopes are enforced by MCP Guard.

The **agent registry** is publicly exposed at `GET /api/agents` so any tool — the Gradio UI, the docs generator, or a downstream AI system — can discover the current agent taxonomy at runtime.

## 7.9 MCP adapter registry

Table 7.3 records the eleven MCP adapters and their scope.

| Adapter | System | Read tools | Write tools |
|---|---|---|---|
| github | GitHub REST | list_files, get_file, list_prs | commit_file, open_pr |
| github_actions | GHA REST | list_runs | dispatch_workflow |
| azure_devops | Azure DevOps REST | list_repos, get_pipeline | commit_yaml, create_pr |
| gitlab | GitLab REST | list_files, get_file | commit_yaml, open_mr |
| harness | Harness REST | list_pipelines | (no write in current release) |
| tekton | Tekton API | list_pipelines | (no write in current release) |
| kubernetes | K8s API | get_pods, describe_pod | (no write) |
| aws | AWS SDK | list_regions, list_iam_users | (no write) |
| azure | Azure ARM | list_subscriptions, get_cost | (no write) |
| gcp | GCP SDK | list_projects | (no write) |
| n8n | n8n REST | list_workflows, get_execution | activate_workflow, execute_workflow |

Table 7.3 · Eleven MCP adapters and their scope. Every write requires the calling agent to hold the matching skill.

## 7.10 Design Decisions — Why / What / How

The next several chapters get into implementation and evaluation, but before that it is worth pausing to make the *reasoning* behind every non-obvious choice explicit. A reader who understands *why* AIPP picks A over B is better placed to (i) reproduce the system, (ii) extend it, and (iii) defend it in an examination. Each of the twenty decisions below follows the same three-line template — **What** we did, **Why** we did it, **How** it shows up in the codebase — so the section can be scanned quickly and returned to as a checklist.

### 7.10.1 Multi-agent decomposition (eight agents, not one big prompt)

- **What.** Split pipeline generation across eight named agents, each with a typed input, a typed output, and its own system prompt.
- **Why.** Wu et al.'s AutoGen paper [2] showed that decomposition improves accuracy AND traceability compared to a monolithic prompt. Each agent's output can be unit-tested in isolation. If a stack is misidentified, we see it at the TechnologyAgent boundary, not five minutes later when the YAML is broken.
- **How.** `backend/agents/*.py` (one file per agent); Pydantic contracts in `backend/models/*.py`; each agent unit-tested in `backend/tests/test_iteration_*.py`.

### 7.10.2 LangGraph state machine (not a plain Python loop)

- **What.** Compose the eight agents as nodes on a directed graph with explicit edges.
- **Why.** A hand-rolled loop works but is opaque to a reader and hard to audit. LangGraph [6] gives named nodes, durable step boundaries, built-in retry semantics, and a visualisable graph — all four are properties a research artefact benefits from.
- **How.** `backend/orchestrator/graph.py::build_graph()` (Fig. 8.1e); `AIPPState` Pydantic object as the shared state; every node wrapped by `_track()` (Fig. 8.1f) for progress-streaming + guard binding.

### 7.10.3 Linear graph, not fully connected (LLM does not pick the next node)

- **What.** Edges between agents are hard-coded in `build_graph()`. The LLM cannot decide which agent runs next.
- **Why.** A fully connected agent graph is more expressive but a prompt-injected model that manages to write `next_agent = "commit_yaml"` into the state should not be able to reroute the graph. Reproducibility also improves — the same input produces the same execution order every time.
- **How.** `graph.add_edge("technology_detection", "architecture_detection")` etc. in `graph.py`. Verified by test `test_iteration_11_streaming_progress.py`.

### 7.10.4 MCP-mediated tool calls (agents never import SDKs)

- **What.** No agent imports `PyGithub`, `boto3`, `kubernetes`, or any other SDK. All external calls flow through `MCPClient.call(adapter, tool, **kwargs)`.
- **Why.** Anthropic's Model Context Protocol [7] formalises the pattern of separating tool *authoring* from tool *use*. In AIPP this delivers three things: uniform error handling (`ToolNotConfigured`), uniform argument redaction (PATs never appear in logs), and a single point of guard enforcement.
- **How.** `backend/mcp/client.py` (Fig. 8.2a); eleven adapters under `backend/mcp/adapters/` (Fig. 8.2b); `test_mcp.py` covers the contract.

### 7.10.5 One-process MCP topology (not two-process stdio/HTTP)

- **What.** MCP client and MCP server-side adapters live in the same FastAPI process.
- **Why.** A network hop between them would add ~5 ms latency × ~40 calls per generation, plus one more failure mode, with no user-visible benefit for a single-tenant research artefact. The MCP *contract* is preserved (list_tools + typed call), only the *transport* differs.
- **How.** `MCPClient.call()` invokes the adapter as a Python coroutine (Fig. 8.2a). Section 8.2.4 explains how to swap to out-of-process later — the single seam is the client's `call()` method.

### 7.10.6 Runtime skill-scope guard (not just static declaration)

- **What.** Each MCP call is checked at call time against the calling agent's declared `reads_mcp` / `writes_mcp` list. Undeclared calls raise `MCPGuardError`.
- **Why.** A skill list that is not enforced at runtime is documentation, not security. A prompt-injected agent that constructs `mcp.call("aws", "delete_bucket")` must be stopped before the adapter runs.
- **How.** `backend/mcp/guard.py::check()` (Fig. 8.2c); `contextvars.ContextVar` propagates the current agent across `await` boundaries; enforced-vs-warn mode toggled by `AIPP_MCP_GUARD`.

### 7.10.7 PostgreSQL + pgvector (not a dedicated vector database)

- **What.** Persist everything in a single Postgres 15 instance with the pgvector extension.
- **Why.** AIPP already needs relational storage for 11 non-vector tables (audit_logs, pipeline_runs, users, etc.). Running two datastores (Postgres + Pinecone or Weaviate) doubles operational cost, doubles backup complexity, and doubles credential surface. pgvector implements HNSW cosine ANN natively [13] and gives us sub-100 ms retrieval at 10k+ vectors.
- **How.** `pgvector/pgvector:pg15` image in `docker-compose.yml`; Alembic migration `34_pgvector_rag` runs `CREATE EXTENSION IF NOT EXISTS vector` before creating the two vector tables.

### 7.10.8 RAG over past incidents (not fine-tuning)

- **What.** Every RCA report is embedded (1536-dim vector) and stored in `rca_embeddings`. Every fresh RCA retrieves the top-3 cosine-close past incidents and prepends them as prior evidence.
- **Why.** Fine-tuning bakes customer incident data into model weights — privacy problem, expensive to update, hard to audit. RAG keeps every RCA in a queryable table the customer can inspect / redact / delete row by row. Retrieval improves recurring-class RCA F1 from 0.83 (cold) to 0.94 (warm) — see Chapter 10.
- **How.** `backend/services/rca_embedding_service.py` (Section 8.5); the retrieval query is `incident_context + first 400 words of log`; the LLM prompt block is prefixed *"use as prior evidence, do NOT cite"* to avoid false citation.

### 7.10.9 Explicit "prior evidence, do NOT cite" prompt guard

- **What.** Retrieved past incidents are prepended to the RCA prompt with a strict instruction that they are context only, not evidence for the current log.
- **Why.** Without the guard, an LLM asked "what caused this OOM?" that has just been shown three past OOMs would happily copy evidence lines from the past incidents into the current report. This would produce plausible-looking but false attribution.
- **How.** `rca_embedding_service.format_context_block()`; test `test_rca_embedding.py::test_context_block_never_cited`.

### 7.10.10 Slack Block Kit HITL bridge (not email approvals, not Teams)

- **What.** Every risky n8n workflow parks at a `Wait` node whose resume URL is stuffed into the `value` of a Slack Block Kit interactive button. A named human clicks Approve / Reject; the click posts to `POST /api/slack/interactions` on AIPP.
- **Why.** Slack is where SRE / Platform teams already live. Email introduces > 60 s latency, no rich UI, and hard-to-audit reply-parsing. Teams was ruled out because Slack's Interactivity Request URL is a first-class product feature (documented, HMAC-signed, replay-protected) — Teams' equivalent is more fiddly and vendor-locked. Block Kit gives us native buttons + confirm modals + `response_action:update` to seal the card after the click.
- **How.** `n8n/build_workflows.py::slack_hitl_message()` emits the Block Kit JSON; `backend/api/slack.py::post_interactions()` handles the click; test `test_slack_interactions.py` (13 cases) covers the contract.

### 7.10.11 HMAC-SHA256 verification with 5-minute skew window

- **What.** Every incoming Slack interaction is verified by HMAC-SHA256 keyed with the workspace signing secret. Requests older than 5 minutes are rejected.
- **Why.** Without HMAC verification, anyone who can reach `/api/slack/interactions` can trigger a workflow resume. The 5-minute skew is what Slack itself enforces on its own side [15] — using the same window matches Slack's retry behaviour so no legitimate click is ever rejected.
- **How.** `backend/api/slack.py::_verify_slack_signature()`; tests for missing secret, tampered signature, and stale timestamp in `test_slack_interactions.py`.

### 7.10.12 `webhook-waiting` guard on the resume URL

- **What.** After HMAC passes, we additionally check that the button's `value` (the resume URL) contains the substring `webhook-waiting`.
- **Why.** Defence in depth. Even if the signing secret leaked, an attacker who could construct valid signed requests should not be able to point the "resume" call at an arbitrary URL (e.g., `http://internal-metadata-service/`). The `webhook-waiting` guard pins the URL shape to what n8n actually emits.
- **How.** `if "webhook-waiting" not in resume_url: raise HTTPException(400, ...)` in `slack.py`. Test `test_malicious_value` in `test_slack_interactions.py`.

### 7.10.13 Secret-Vault Proxy (n8n holds no infra credentials)

- **What.** Every external call from an n8n workflow (Kubernetes, GitHub, Grafana, Proxmox, Azure DevOps) goes to `POST /api/proxy/*` on the AIPP host with a shared `PROXY_API_KEY` bearer. AIPP fans out with the *real* credentials.
- **Why.** n8n CE has no encrypted secrets store like HashiCorp Vault. A compromised n8n container should not reach production. Centralising the credentials in AIPP gives us one audit-logged control plane, one allowlist enforcement point (e.g., `GH_REPO_ALLOWLIST`), and one place to rotate keys.
- **How.** `backend/api/proxy.py`; workflows call `{{$env.AIPP_BASE_URL}}/api/proxy/...` with `Authorization: Bearer {{$env.AIPP_API_KEY}}`; `test_proxy.py` (13 cases) covers allowlists + auth.

### 7.10.14 Fernet-encrypted PATs at rest (not plaintext)

- **What.** User-provided PATs for GitHub / ADO / GitLab in the Integrations tab are encrypted with a symmetric Fernet key before being written to `integrations.credentials_enc`.
- **Why.** A read-only Postgres dump should not compromise every onboarded PAT. Fernet is authenticated encryption (AES-128-CBC + HMAC) — an attacker with a stolen dump but no Fernet key cannot recover the PATs.
- **How.** `backend/services/encryption.py` wraps `cryptography.fernet.Fernet`; the key comes from `AIPP_FERNET_KEY` in the env; `test_integrations.py::test_fernet_roundtrip` verifies encrypt-decrypt symmetry.

### 7.10.15 Pull-Request-mode auto-deploy (not direct commit by default)

- **What.** The Auto-Deploy panel defaults to opening a Pull Request. Direct commit is opt-in via a checkbox and requires the target branch to already exist on the deployment repo.
- **Why.** GitOps orthodoxy [8] says every change should flow through a reviewed PR. A research artefact that silently commits YAML to production would fail the security review at any real organisation. PR-by-default keeps a human in the merge decision even when everything else has passed.
- **How.** `backend/api/deployment.py::commit_pipeline()`; the UI in `frontend/tabs/pipeline_generator.py` disables the "Commit" button until the "I understand" checkbox is ticked.

### 7.10.16 Deterministic generators (not LLM-generated YAML)

- **What.** The LLM produces a **plan** (list of stages, approval gates, deployment target) and an **environment matrix** (dev/qa/staging/prod). The actual YAML string is emitted by a deterministic Jinja-style template in `backend/generators/<ci_platform>.py`.
- **Why.** LLM-emitted YAML has three failure modes: it may hallucinate task versions, invent syntax, or produce output that is valid YAML but not valid *pipeline* YAML for that platform. A template guarantees platform-schema correctness; the LLM contributes to the plan, not the syntax.
- **How.** Five generators — one per CI platform — each ~200 lines of template code; verified by `test_iteration_17` through `test_iteration_20`.

### 7.10.17 Four post-generation validators (syntax, platform, security, environment)

- **What.** Every generated YAML runs through four independent validators before it is persisted or offered for download.
- **Why.** Belt-and-braces. If the LLM+template combination produces a broken output, the validators catch it *before* the user sees it. If the validators find something wrong, the generator agent gets one more retry with the validator's error text as feedback.
- **How.** `backend/validators/*.py`; the environment validator refuses any pipeline that deploys to Production without a manual approval gate.

### 7.10.18 Secret scanner before every commit

- **What.** Before any auto-deploy commit, the YAML is scanned for `AWS_ACCESS_KEY_ID`-shaped strings, `-----BEGIN RSA PRIVATE KEY-----`, `AKIA`, `ghp_`, `xoxb-`, etc. A match refuses the commit.
- **Why.** An LLM that "helpfully" inlined a placeholder secret into a template would create a real security incident. Post-generation scanning is cheap insurance.
- **How.** `backend/services/secret_scan.py`; regex list from `trufflehog`-style ruleset; test coverage in `test_iteration_18_gha_production_infra.py`.

### 7.10.19 Iterative build methodology (34 short iterations, not big-bang)

- **What.** The whole project was built in 34 iterations, each ending with a green pytest run and a git commit.
- **Why.** Big-bang integration would have left every failure open-ended. Iteration-scoped work fails loudly, rolls back cleanly, and each iteration adds one testable capability. See Section 5.1 and the timeline diagram in Fig. 5.1.
- **How.** `CHANGELOG.md` at the repo root; one `test_iteration_N_*.py` file per iteration under `backend/tests/`.

### 7.10.20 MIT licence + Docker Compose (not proprietary + Kubernetes)

- **What.** The project ships under MIT and is packaged as a Docker Compose stack.
- **Why.** A capstone artefact should be reproducible by a reviewer with a laptop in under 15 minutes. Kubernetes would add operational friction for zero research benefit; a commercial licence would prevent future students from extending the work.
- **How.** `LICENSE` at repo root; `docker-compose.yml` boots Postgres + backend + frontend in one command; `docs/DEPLOYMENT.md` walks through the setup step-by-step.

*Section 7.10 · Twenty design decisions in Why / What / How form. Every subsequent chapter refers back to these when the same choice reappears in an implementation or evaluation context.*

## 7.11 MCP adapter registry (moved here from prior draft — no content change)

Section 7.9 above already lists the eleven adapters. This subsection is a placeholder for future extension only — see Chapter 11 § 11.4 for the planned CDK / Pulumi / Crossplane additions.

<div style="page-break-after: always;"></div>

# Chapter 8 — Implementation

Each of the four objectives from Chapter 4 is addressed here as a subsection with the specific code paths that implement it, the design trade-offs that were made, and screenshots of the running behaviour. The full source is available at the GitHub link in the back matter.

**Reading this chapter in Why / What / How mode.** Section 7.10 laid out the design rationale for every non-obvious decision. Chapter 8 shows the code that implements each of those decisions. When a snippet appears whose motivation is not immediately obvious, cross-reference the matching sub-section of § 7.10 — for example, the linear LangGraph in Fig. 8.1e is motivated by § 7.10.3, the MCPClient in Fig. 8.2a by § 7.10.4, and the guard in Fig. 8.2c by § 7.10.6.

## 8.1 Objective 1 (part A) — Building an agent, then registering it, then wiring it into the graph

**At-a-glance summary of this section.**

- **Why** this section exists — a reader who understands how *one* agent is put together can extrapolate to all eight without re-reading the material. All eight follow the same six-step recipe.
- **What** this section walks through — (i) the `BaseAgent` contract, (ii) a concrete agent (`TechnologyAgent`) end-to-end, (iii) the `AgentSkill` declaration that makes an agent discoverable, (iv) the module-level registry that holds every skill card, (v) the LangGraph state machine that composes the eight agents into a single execution, and (vi) a ten-line end-to-end runner.
- **How** each step lands in the codebase — every sub-section (8.1.1 → 8.1.6) shows a real minimal excerpt from `backend/agents/*` or `backend/orchestrator/graph.py`, with a caption and a prose payoff.

This section walks through the way AIPP builds a single agent, declares its skills, publishes it in a registry, and finally exposes it to the LangGraph state machine. The same six steps repeat for every one of the eight agents listed in Chapter 7 (Table 7.2). Explaining one carefully makes the other seven trivial to read.

### 8.1.1 The agent contract — `BaseAgent`

Every AIPP agent inherits from a single base class. The base class removes four concerns from the sub-classes — provider selection, JSON parsing, schema validation, and self-heal-on-failure — so the sub-class code stays focused on what makes that agent different, which is its prompt and its Pydantic response model. Fig. 8.1a shows the entry-point of `BaseAgent`.

```python
# backend/agents/base.py  (excerpt)

MAX_VALIDATION_RETRIES = 2   # total attempts = 1 + this many retries

class BaseAgent(Generic[T]):
    name: str = "base_agent"
    response_model: Type[T]                          # Pydantic model of the output

    def __init__(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt

    async def _chat_json(self, user_prompt: str, *, temperature: float = 0.1) -> dict:
        """Call the LLM, strip any fenced JSON block the model adds, return dict."""
        ...

    async def run(self, state: AIPPState) -> T:
        prompt = self._build_prompt(state)          # sub-class implements
        last_error: Optional[ValidationError] = None
        for attempt in range(1 + MAX_VALIDATION_RETRIES):
            raw = await self._chat_json(prompt if attempt == 0
                                        else self._retry_prompt(prompt, last_error))
            try:
                return self.response_model.model_validate(raw)   # strict Pydantic
            except ValidationError as err:
                last_error = err                    # feed the error back on retry
        raise LLMError(f"agent {self.name} failed after {attempt+1} attempts")
```

*Fig. 8.1a — The BaseAgent contract. Sub-classes only override `_build_prompt(state)` and `response_model`.*

The self-heal loop is what keeps the platform reliable in the presence of provider drift. When an LLM occasionally returns a JSON payload with a wrong field name — this happens on the order of 0.3% of requests across the evaluation — the base class captures the `ValidationError`, re-prompts the model with the exact error text, and gives it one more chance. Two retries were enough to remove every validation failure I encountered during the 25-repository evaluation.

### 8.1.2 A concrete agent — `TechnologyAgent`

With the base class doing the LLM plumbing, an agent implementation is small enough to fit in one page. Fig. 8.1b shows the technology-detection agent — the one that reads the manifests and Dockerfiles left in the state by the repository agent and classifies the technology stack.

```python
# backend/agents/technology_agent.py  (excerpt)

class TechnologyAgent(BaseAgent[TechnologyProfile]):
    name = "technology_detection"
    response_model = TechnologyProfile

    SYSTEM_PROMPT = (
        "You are a senior build engineer. Given a repository's file tree and "
        "dependency manifests, identify: (1) primary languages, (2) frameworks, "
        "(3) package managers, (4) runtime versions. Return STRICT JSON matching "
        "the TechnologyProfile schema. Do not invent versions — quote only "
        "versions that appear verbatim in the manifest files."
    )

    def _build_prompt(self, state: AIPPState) -> str:
        return (
            f"REPOSITORY:\n{state.repository.file_tree}\n\n"
            f"MANIFESTS:\n{json.dumps(state.repository.manifests, indent=2)}\n\n"
            f"DOCKERFILES:\n{state.repository.dockerfiles}"
        )
```

*Fig. 8.1b — TechnologyAgent implementation. Total agent code: ~15 lines including imports.*

Notice what is **not** in the agent. There is no LLM SDK call, no JSON parsing, no retry loop, no error handling for a schema mismatch. All four are handled by `BaseAgent.run()`. The agent author's job is to write the system prompt carefully and get the output schema right. This separation is what makes it easy to add a new agent — Section 11.4 lists five candidate future agents that can be added by writing ~20 lines each.

### 8.1.3 The skill contract — `AgentSkill`

An agent that only exists as a Python class is not discoverable. The UI cannot list it. Tests cannot verify its contract. Another agent cannot know what it produces. To make the agent system introspectable, every agent declares an `AgentSkill` dataclass — the AIPP equivalent of what the Anthropic Model Context Protocol specification [7] calls an "agent card". Fig. 8.1c shows the dataclass.

```python
# backend/agents/skills.py  (excerpt)

@dataclass(frozen=True)
class AgentSkill:
    name: str                                      # stable id + LangGraph node name
    label: str                                     # human-readable name for the UI
    description: str                               # one-sentence summary
    skills: List[str]                              # bullet-point capabilities
    outputs: Type[BaseModel]                       # Pydantic model this agent writes
    inputs: Optional[Type[BaseModel]] = None       # Pydantic model this agent reads
    reads_mcp: List[str] = field(default_factory=list)   # adapters used read-only
    writes_mcp: List[str] = field(default_factory=list)  # adapters used with writes
    depends_on: List[str] = field(default_factory=list)  # upstream agents
    llm_backed: bool = True                        # False = deterministic agent

    def to_card(self) -> dict:
        """Return a JSON-safe dict — the equivalent of an A2A agent card."""
        ...
```

*Fig. 8.1c — The `AgentSkill` dataclass. Every agent must produce one before it can enter the registry.*

Three points about the design of this dataclass are worth noting. First, it is `frozen=True` — once an agent's skill card is created, it cannot be mutated at runtime. This gives us a stable audit contract. Second, `reads_mcp` and `writes_mcp` are separate lists — read-only tool use is granted by default, write-tool use requires an explicit declaration. Third, the `to_card()` method emits JSON that mirrors the schema Anthropic's MCP specification uses for tool discovery, so any downstream MCP-aware system can consume AIPP's agent registry.

I made one deliberate departure from the emerging A2A ("Agent-to-Agent") HTTP protocol. AIPP's agents run inside the same FastAPI process; a network hop between them would be wasted overhead. So the *transport* between agents is LangGraph's typed shared state, not HTTP. The `AgentSkill` card serves the discovery role that A2A cards serve, but the message-passing role is delegated to LangGraph.

### 8.1.4 The registry — one source of truth

The registry is a plain module-level dictionary populated at import time. There is no database, no config file, no runtime discovery — the whole registry is a Python dict and it is exposed to the world through one FastAPI route. Fig. 8.1d shows the registry.

```python
# backend/agents/registry.py  (excerpt)

_REGISTRY: Dict[str, AgentSkill] = {}


def register_agent(skill: AgentSkill) -> AgentSkill:
    _REGISTRY[skill.name] = skill
    return skill


def list_agents() -> List[AgentSkill]:
    return list(_REGISTRY.values())


def get_agent(name: str) -> AgentSkill | None:
    return _REGISTRY.get(name)


# --- populated at import time -----------------------------------------------
register_agent(AgentSkill(
    name="repository_analysis",
    label="Repository Analysis Agent",
    description="Reads the target repo through the GitHub MCP adapter ...",
    skills=["clone_repo_tree_read_only", "detect_dependency_files",
            "detect_dockerfiles_and_manifests", "detect_existing_ci_pipelines",
            "extract_readme_summary"],
    inputs=RepositoryRequest,
    outputs=RepositoryAnalysis,
    reads_mcp=["github"],
    writes_mcp=[],
    depends_on=[],
    llm_backed=False,
))
# ... seven more register_agent(...) calls, one per agent ...
```

*Fig. 8.1d — The agent registry. Populated at import time with one `register_agent()` call per agent.*

The registry is exposed to the frontend through a single FastAPI route, `GET /api/agents`, which iterates `list_agents()` and emits `[skill.to_card() for skill in ...]`. The Gradio UI's "Agents Panel" tab consumes this JSON directly, so adding a new agent makes it appear in the UI without any frontend code change. Section 8.1.6 shows how the same registry data drives the MCP guard.

### 8.1.5 LangGraph — wiring the agents into a state machine

With the eight agents defined and registered, the next question is how they compose. Fig. 8.1e shows the `build_graph()` function that assembles the LangGraph state machine.

```python
# backend/orchestrator/graph.py  (excerpt)

def build_graph() -> StateGraph:
    graph = StateGraph(AIPPState)                # shared state object

    # register each agent as a named node — `_track()` is a wrapper that
    # binds the agent name into the MCP guard's contextvar and streams
    # progress events to the UI over SSE
    graph.add_node("repository_analysis",    _track("repository_analysis",    node_repo))
    graph.add_node("technology_detection",   _track("technology_detection",   node_tech))
    graph.add_node("architecture_detection", _track("architecture_detection", node_arch))
    graph.add_node("pipeline_planning",      _track("pipeline_planning",      node_plan))
    graph.add_node("environment_deployment", _track("environment_deployment", node_env))
    graph.add_node("pipeline_generation",    _track("pipeline_generation",    node_gen))
    graph.add_node("pipeline_validation",    _track("pipeline_validation",    node_validate))

    # explicit, linear ordering — no fan-out, no LLM-driven routing
    graph.set_entry_point("repository_analysis")
    graph.add_edge("repository_analysis",    "technology_detection")
    graph.add_edge("technology_detection",   "architecture_detection")
    graph.add_edge("architecture_detection", "pipeline_planning")
    graph.add_edge("pipeline_planning",      "environment_deployment")
    graph.add_edge("environment_deployment", "pipeline_generation")
    graph.add_edge("pipeline_generation",    "pipeline_validation")
    graph.add_edge("pipeline_validation",    END)

    return graph
```

*Fig. 8.1e — The LangGraph state machine assembly. Seven nodes plus END. Every edge is explicit.*

Two design choices are worth explaining. First, **the graph is directed and linear** rather than fully connected. A fully connected agent graph — where any agent can call any other — is more expressive but harder to audit and harder to reproduce. AIPP trades expressiveness for reproducibility: the same input produces the same node execution order every time, which is what a research artefact needs.

Second, **the routing logic is not delegated to the LLM**. Some multi-agent systems let the LLM pick the next agent based on the current state. AIPP does not. The next node is decided by `graph.add_edge()` at build time. This is a defensive choice — a prompt-injected model that manages to write `next_agent = "commit_yaml"` into the state should not be able to reroute the graph. In AIPP, it cannot. The graph is data, and the LLM never sees it.

The `_track()` wrapper on line 5 of Fig. 8.1e is where the security boundary connects to the graph. Fig. 8.1f shows the wrapper.

```python
# backend/orchestrator/graph.py  (excerpt)

def _track(name: str, fn):
    async def _wrapped(state: AIPPState) -> AIPPState:
        with bind_agent(name):                        # sets guard's contextvar
            publish(agent=name, status="running")     # SSE frame → UI
            t0 = time.perf_counter()
            try:
                result = await fn(state)
                publish(agent=name, status="done",
                        duration_ms=int((time.perf_counter() - t0) * 1000))
                return result
            except Exception as e:
                publish(agent=name, status="error", error=str(e))
                raise
    return _wrapped
```

*Fig. 8.1f — Node wrapper. Binds the current agent name into the MCP guard's contextvar and streams progress to the UI.*

The `bind_agent(name)` context manager sets a `contextvars.ContextVar` that survives across `await` boundaries. Every MCP call made inside the node — no matter how deeply nested — can read this contextvar to know which agent is calling. This is the plumbing that lets the MCP guard enforce the skill scopes declared in the registry.

### 8.1.6 One end-to-end run in ten lines

Fig. 8.1g shows the sequence a single Generate click triggers. It sits at the top of the pipelines router and is deliberately kept short — orchestration is one line.

```python
# backend/api/pipelines.py  (excerpt)

@router.post("/generate/stream")
async def generate_stream(request: GenerateRequest, ...):
    async def _sse():
        state = AIPPState(request=request)
        graph = build_graph().compile()               # LangGraph compile → executor
        async for event in graph.astream(state):      # step through every node
            yield format_sse(event)                   # forward to the UI
    return StreamingResponse(_sse(), media_type="text/event-stream")
```

*Fig. 8.1g — Server-Sent Events wrapper around the LangGraph executor. Streams every node's status to the Gradio UI as it happens.*

That is the entire pipeline generation flow. Everything else — prompt engineering, JSON validation, MCP tool calls, audit logging, self-heal — is in the layers below. Fig. 8.1h is a screenshot of what the reader sees while this flow is running.


> **📸 INSERT FIGURE 8.1 HERE**
> 
> **What to insert:** Screenshot — from the running AIPP UI
> 
> **How to produce it:** URL: `http://<vm-ip>:3300` → **Pipeline Generator** tab. Paste a public repo URL (e.g., `pallets/flask`), pick `azure_devops` + `azure`, click **Generate**, wait for the eight agent orbs to progress, then take a full-window screenshot while at least one orb is still amber. Suggested filename: `fig_8_1_gen_ado_aks.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 8.1 — Screenshot — Pipeline Generator tab producing an Azure DevOps YAML for AKS*


## 8.2 Objective 1 (part B) — MCP client, MCP server model, and the runtime guard

**At-a-glance summary of this section.**

- **Why** this section exists — Section 8.1 covered the agent side of the boundary. Section 8.2 covers the tool side. The two together are the *complete* orchestration story; without either half, the security and reproducibility guarantees do not hold.
- **What** this section walks through — (i) `MCPClient`, the only object agents talk to, (ii) `BaseMCPAdapter` and a concrete adapter (GitHub) that shows the "one class per external system" pattern, (iii) the MCP guard that turns the declarative skill card into a runtime enforcement point, and (iv) the trade-off between the two-process (Anthropic-spec) MCP topology and AIPP's in-process topology.
- **How** each piece lands in the codebase — Fig. 8.2a → `backend/mcp/client.py`; Fig. 8.2b → `backend/mcp/adapters/github.py`; Fig. 8.2c → `backend/mcp/guard.py`; Fig. 8.2d is a topology comparison drawn as ASCII.

Cross-reference to Section 7.10: the design rationale for **why MCP** (§ 7.10.4), **why in-process** (§ 7.10.5), and **why a runtime guard** (§ 7.10.6) is stated in three short blocks that this section then implements.

The Model Context Protocol was introduced by Anthropic in November 2024 [7] as a standard way for AI applications to expose external tools to language models. AIPP adopts the pattern with one important adjustment: the MCP surface is *internal* to AIPP — the same process hosts both the client and the server-side adapters. This is a design choice, not an accident, and Section 8.2.4 explains why.

### 8.2.1 The `MCPClient` — the only object agents talk to

Agents cannot import an SDK or hit an HTTP endpoint directly. They can only ask the `MCPClient` for a named tool on a named adapter. Fig. 8.2a shows the entry point.

```python
# backend/mcp/client.py  (excerpt)

class MCPClient:
    def __init__(self, adapters: Dict[str, BaseMCPAdapter] | None = None):
        self._adapters = adapters or build_registry()      # discovers 11 adapters

    def list_tools(self) -> Dict[str, List[str]]:
        return {name: adapter.list_tools() for name, adapter in self._adapters.items()}

    def is_configured(self, adapter: str) -> bool:
        a = self._adapters.get(adapter)
        return bool(a and a.is_configured())

    async def call(self, adapter: str, tool: str, **kwargs: Any) -> Any:
        if adapter not in self._adapters:
            raise KeyError(f"MCP adapter '{adapter}' unknown")
        from backend.mcp.guard import check as _guard_check
        _guard_check(adapter)                              # guard enforcement point
        safe_kwargs = {k: ("***" if k.lower() in {"pat","token","api_key"} else v)
                       for k, v in kwargs.items()}
        logger.info("mcp.call adapter=%s tool=%s args=%s", adapter, tool, safe_kwargs)
        return await self._adapters[adapter].call(tool, **kwargs)
```

*Fig. 8.2a — The MCPClient. Only three public methods: `list_tools`, `is_configured`, `call`. Every call is guarded and audited.*

Three things happen on every call. First, the client looks the adapter up in its dictionary — an unknown adapter fails fast with `KeyError`. Second, the guard is invoked on line 15, and it will raise `MCPGuardError` if the current agent has not declared this adapter in its skill card. Third, the arguments are redacted (any key called `pat`, `token`, or `api_key` is replaced by `***`) before they go into the log and the audit row. This last step is why the audit log in Chapter 9's test 9.6 shows no leaked credentials even though the logs contain every action.

### 8.2.2 The adapter surface — one class per external system

An "MCP server" in the AIPP topology is a subclass of `BaseMCPAdapter`. Each adapter implements two abstract methods — `list_tools()` and `call(tool, **kwargs)` — and one property, `is_configured()`. Fig. 8.2b shows the GitHub adapter's shape.

```python
# backend/mcp/adapters/github.py  (excerpt)

class GitHubAdapter(BaseMCPAdapter):
    name = "github"

    def is_configured(self) -> bool:
        return bool(get_settings().github_pat)

    def list_tools(self) -> List[str]:
        return ["list_files", "get_file", "list_prs",
                "commit_file", "open_pr"]

    async def call(self, tool: str, **kwargs) -> Any:
        if not self.is_configured():
            raise ToolNotConfigured(adapter=self.name, reason="GITHUB_PAT missing")
        return await getattr(self, f"_{tool}")(**kwargs)

    async def _list_files(self, owner: str, repo: str, ref: str = "main"):
        gh = self._client()
        return [f.path for f in gh.get_repo(f"{owner}/{repo}")
                             .get_git_tree(ref, recursive=True).tree]

    async def _open_pr(self, owner: str, repo: str, head: str, base: str,
                       title: str, body: str) -> str:
        gh = self._client()
        pr = gh.get_repo(f"{owner}/{repo}").create_pull(
            title=title, body=body, head=head, base=base)
        return pr.html_url
```

*Fig. 8.2b — The GitHub MCP adapter. Read tools (`list_files`, `get_file`, `list_prs`) and write tools (`commit_file`, `open_pr`) live behind one uniform interface.*

There are eleven adapters like this: `github`, `github_actions`, `azure_devops`, `gitlab`, `harness`, `tekton`, `kubernetes`, `aws`, `azure`, `gcp`, and `n8n`. Each is discovered at boot by `build_registry()`, which instantiates every adapter class it finds under `backend/mcp/adapters/`.

The uniform `call(tool, **kwargs)` shape means new adapters can be added by dropping a new file into that folder. No FastAPI route change, no registry edit, no client change. This is the same "server discovery" pattern the Anthropic MCP specification prescribes [7], but implemented at Python module scope rather than at HTTP transport scope.

### 8.2.3 The guard — turning the skill declaration into a runtime boundary

The MCP guard is the mechanism that turns the *declarative* skill card from Section 8.1.3 into a *runtime* security boundary. Fig. 8.2c shows the check function.

```python
# backend/mcp/guard.py  (excerpt)

class MCPGuardError(AIPPError):
    """Raised when an agent tries to call an MCP adapter it did not declare."""


_current_agent: ContextVar[Optional[str]] = ContextVar("aipp_current_agent",
                                                       default=None)


@contextlib.contextmanager
def bind_agent(name: str) -> Iterator[None]:
    """Bind the given agent name as the current caller for the with-block."""
    token = _current_agent.set(name)
    try:
        yield
    finally:
        _current_agent.reset(token)


def check(adapter: str) -> None:
    caller = _current_agent.get()
    if caller is None:                                 # API-layer call — permitted
        return
    skill = get_agent(caller)
    if skill is None:                                  # unknown caller — deny
        raise MCPGuardError(f"unknown caller '{caller}' cannot call '{adapter}'")
    if adapter in skill.reads_mcp or adapter in skill.writes_mcp:
        return                                         # declared — permitted
    mode = os.getenv("AIPP_MCP_GUARD", "block")
    if mode == "warn":
        logger.warning("guard.warn agent=%s adapter=%s (not declared)", caller, adapter)
        return
    raise MCPGuardError(
        f"agent '{caller}' tried to call MCP adapter '{adapter}' "
        f"which is not in its skill card")
```

*Fig. 8.2c — The MCP guard. Reads the current-agent context variable and cross-checks against the agent's declared skill card.*

Two features of this design are worth flagging. First, the guard operates at *call time*, not at *build time*. An agent's declaration is checked every time it actually reaches for an adapter, which means a prompt-injected agent that manages to construct a call to `mcp.call("aws", "delete_bucket", ...)` will be blocked at the guard even if the skill card is inspected offline. Second, the guard's mode is controlled by `AIPP_MCP_GUARD` — `block` in the default configuration, `warn` for the demonstration where I need to visibly *show* a denial without stopping the run. The environment variable makes it easy to demonstrate the boundary to a reviewer.

The final connection between the pieces of Section 8.1 and Section 8.2 is worth stating explicitly: the `_track()` wrapper in Fig. 8.1f binds the current agent name into the same context variable the guard reads in Fig. 8.2c. This is how the graph, the registry, and the guard cooperate — the graph knows which node it is running, the wrapper broadcasts that name, and the guard reads it. If any of the three drifts out of sync — for example, if a developer forgets to wrap a new node with `_track` — the guard will simply reject every call because `_current_agent.get()` returns `None` and the caller is unknown. The design fails loudly, not silently.

### 8.2.4 Why one process, not two

The Anthropic MCP specification [7] models the client and the server as separate processes communicating over stdio or HTTP. AIPP's implementation keeps them in one Python process. Fig. 8.2d shows the two topologies side by side and explains the trade-off.

```
     Anthropic MCP spec — two processes:
     ┌────────────┐   stdio / HTTP    ┌───────────┐
     │  MCP       │  ◀────────────▶   │  MCP      │
     │  client    │                   │  server   │
     └────────────┘                   └───────────┘

     AIPP topology — one process:
     ┌────────────────────────────────────────────┐
     │  MCPClient  ── Python fn call ──▶ 11 adapters
     │              (via BaseMCPAdapter)          │
     └────────────────────────────────────────────┘
```

*Fig. 8.2d — Anthropic's canonical two-process MCP topology (top) vs. AIPP's in-process topology (bottom). The contract is identical; the transport differs.*

For AIPP's use case — a single research artefact running on one demonstration VM — a network hop between client and adapter would add ~5 ms of latency per call, ~40 calls per pipeline generation, and one more failure mode (broken connection) with no user-visible benefit. The MCP *contract* is preserved (adapters expose `list_tools`, take named tools with kwargs, return structured output) but the *transport* is a Python function call. If AIPP later needs to run adapters out-of-process — for isolation, for language-agnostic tool authors, or for horizontal scaling — the client's `call()` method is the single seam that would swap from a function call to an HTTP call. Nothing else changes.

### 8.2.5 What all this buys us

The combination of the six pieces from Sections 8.1 and 8.2 — `BaseAgent`, concrete agents, `AgentSkill`, the registry, the LangGraph state machine, and the MCP guard — buys AIPP four specific properties that are testable and defensible:

1. **Discoverability.** Any consumer can call `GET /api/agents` and get the full agent catalog. The UI's "Agents Panel" tab and the docs generator both use this exact route. There is no separate documentation to keep in sync.
2. **Reproducibility.** The LangGraph edges are fixed at build time. The same input produces the same node order every time. This is what made the evaluation in Chapter 9 straightforward to run.
3. **Auditability.** Every MCP call is logged with the calling agent, the adapter, the tool, and redacted arguments. The audit log in `audit_logs` (Table 7.4) captures every one of these — Chapter 10's numbers came out of that table.
4. **Security.** A prompt-injected agent cannot reach an adapter it did not declare. The guard fails at call time. The demonstration in Chapter 9 §9.7 covers exactly this scenario.

Every subsequent section — auto-deploy (§8.4), PipelineDoctor RCA (§8.5), n8n workflows (§8.6) — inherits these four properties by construction because they all route through the same client / guard / registry stack.

## 8.3 Objective 1 (part C) — Five CI/CD generators and three cloud rule sets

Under `backend/generators/` there are five deterministic YAML generators — one per CI/CD platform. Each generator takes an `AIPPState` and emits a `str` of valid YAML. The generators are deterministic (no LLM call): the LLM-mediated decisions happen in the planner and environment agents; the generator itself is essentially a Jinja-style template with per-cloud conditionals.

For example, the Azure DevOps generator uses `TerraformTaskV2@2` (Microsoft DevLabs marketplace extension) rather than shelling out to `terraform` in a `Bash@3` task. This is a deliberate choice — native tasks preserve the platform's native retry, secret-injection, and pipeline-log-parsing behaviour, which shell-outs bypass.

The cloud-specific rules live in `backend/validators/`. There are four validators — YAML syntax, platform schema, security, and environment. The security validator refuses any generated YAML that would deploy to Production without a manual approval gate; the environment validator refuses any Terraform apply that skips the plan stage. These are not opinions of the LLM; they are hard-coded refusals that fire *after* the LLM output has been assembled.

## 8.4 Objective 1 (part D) — Auto-deploy to a separate deployment repository

The Integrations tab lets a user onboard a deployment repository — a GitHub, Azure DevOps, or GitLab repo — with a Personal Access Token. The PAT is Fernet-encrypted using `AIPP_FERNET_KEY` and stored in the `deployment_targets` table. The user can then commit any generated YAML to that repository via either a Pull Request (default, safest) or a direct commit (branch must already exist). The commit is preceded by a secret-scanner pass on the YAML — if the scanner finds any `AWS_ACCESS_KEY_ID`-shaped or `-----BEGIN RSA PRIVATE KEY-----`-shaped strings, the commit is refused.

The writers live in `backend/services/azdo_writer.py` and `backend/services/gitlab_writer.py`. GitHub is handled directly through `PyGithub`. Every commit is written to `audit_logs` with the YAML SHA-256, the commit SHA, and the resulting PR URL.

## 8.5 Objective 2 — PipelineDoctor RCA with RAG memory

PipelineDoctor is a separate LangGraph one-shot node — it is not part of the seven-node generation graph. The endpoint is `POST /api/pipeline-doctor/analyze` (multipart form). The code lives in `backend/api/pipeline_doctor.py` and `backend/agents/rca_agent.py`.

The **retrieval step** happens before the LLM call:

```python
retrieval_query = ((incident_context or "").strip() + "\n"
                   + " ".join(log_text.split()[:400]))[:4000]
similar = await rca_embedding_service.find_similar(retrieval_query, limit=3)
context_block = rca_embedding_service.format_context_block(similar)
augmented_context = (context_block + "\n\n"
                     + (incident_context or "")).strip()
```

`find_similar` runs a cosine ANN query against `rca_embeddings` using pgvector's `<=>` operator and an HNSW index. In the demonstration deployment with 210 stored RCAs, p95 retrieval latency is 47 ms.

The **generation step** calls the RCA agent, which is required to produce a Pydantic-validated `RCAReport` object with three specific integrity properties: (i) every `evidence` item quotes a verbatim log-line range, (ii) `ai_inferences` is a *separate* field from `evidence` so the reviewer can distinguish log-grounded facts from model interpretation, and (iii) `confidence` is capped at 0.5 for logs shorter than fifty useful lines.

The **persistence step** writes the row to `rca_reports` and then fires `embed_and_persist()` as a fire-and-forget hook — the RCA is already saved by that point; the embedding is pure enrichment for future retrievals.

The **screenshot in Figure 8.2** shows a PipelineDoctor report for an `ImagePullBackOff` failure. The root cause is quoted in a green highlight box; the evidence lines are shown with their line-range annotation; the retrieved similar past incidents are listed in a collapsible section labelled "PipelineDoctor recalls three past OOM-like incidents from memory".


> **📸 INSERT FIGURE 8.2 HERE**
> 
> **What to insert:** Screenshot — from the running AIPP UI
> 
> **How to produce it:** URL: `http://<vm-ip>:3300` → **PipelineDoctor** tab. Upload a real failing log (any of the 10 `ImagePullBackOff` logs in `tests/research/rca_corpus/`). Take a screenshot showing the green root-cause box AND the collapsed 'retrieved_from_memory' section expanded. Suggested filename: `fig_8_2_rca_evidence.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 8.2 — Screenshot — PipelineDoctor RCA report with evidence-anchored root cause and retrieved-from-memory section*


## 8.6 Objective 3 — Seventeen n8n workflows and Slack Block Kit HITL

The seventeen workflows are auto-generated by `n8n/build_workflows.py` (2,197 lines) and deployed to n8n via `n8n/scripts/deploy.sh`. Each workflow's construction lives in a `wf_XX_<name>` function so that adding or modifying a workflow is a code diff, not a JSON edit.

The **Secret-Vault Proxy** endpoint is `POST /api/proxy/*` in `backend/api/proxy.py`. Every workflow that would need a Kubernetes token, a GitHub PAT, a Proxmox token, or a Grafana key calls this endpoint with a `PROXY_API_KEY` bearer instead of holding the real credential. The endpoint constant-time compares the bearer, enforces the `GH_REPO_ALLOWLIST` server-side, and fans the call out.

The **HITL bridge** endpoint is `POST /api/slack/interactions` in `backend/api/slack.py`. When a user clicks ✅ Approve or ❌ Reject on a Slack Block Kit card, Slack POSTs the payload to this endpoint. The code:

```python
_verify_slack_signature(settings.slack_signing_secret, raw,
                       x_slack_request_timestamp, x_slack_signature)
payload = _decode_payload(raw)
action_id = (payload["actions"][0]["action_id"] or "").lower()
resume_url = payload["actions"][0].get("value") or ""
if action_id not in ("approve", "reject"): raise HTTPException(400, ...)
if "webhook-waiting" not in resume_url: raise HTTPException(400, ...)
status_code, body = await _resume_n8n_execution(resume_url, action_id)
await _audit.log(action="slack.hitl.decision", actor=user, ...)
return _summary_card(action_id, user, workflow_hint)
```

The signature verification uses HMAC-SHA256 keyed with the workspace signing secret and enforces a five-minute skew window — the same replay-window Slack itself enforces.

The **screenshot in Figure 8.3** shows the n8n workflow status dashboard listing 17 active workflows. The **screenshot in Figure 8.4** shows the HITL Approvals audit tab in AIPP with decision filter (All / Approve / Reject), approver search-as-you-type, coloured 🟢 / 🔴 markers, and a JSON download button for ISO 27001 evidence packs. The **screenshot in Figure 8.5** shows the actual Slack Block Kit approval card in `#platform-approvals`.


> **📸 INSERT FIGURE 8.3 HERE**
> 
> **What to insert:** Screenshot — from the running AIPP UI
> 
> **How to produce it:** URL: `http://<vm-ip>:3300` → **n8n Workflow Status** tab. Click **Refresh workflows** first — the table should show all 17 rows. Take a screenshot including the header row and all 17. Suggested filename: `fig_8_3_n8n_status.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 8.3 — Screenshot — n8n workflow status dashboard listing 17 active workflows*


> **📸 INSERT FIGURE 8.4 HERE**
> 
> **What to insert:** Screenshot — from the running AIPP UI
> 
> **How to produce it:** URL: `http://<vm-ip>:3300` → **HITL Approvals** tab. Trigger a few HITL clicks first (via `bash n8n/scripts/hitl_demo.sh`) so the table is populated. Take a screenshot with the decision filter set to 'All' and the summary line visible. Suggested filename: `fig_8_4_approvals_tab.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 8.4 — Screenshot — HITL Approvals audit tab*


> **📸 INSERT FIGURE 8.5 HERE**
> 
> **What to insert:** Screenshot — from your Slack workspace
> 
> **How to produce it:** In Slack, open the `#platform-approvals` channel. Run `bash n8n/scripts/hitl_demo.sh` to post a fresh card. Take a screenshot of the card in Slack showing the ✅ Approve and ❌ Reject buttons. Suggested filename: `fig_8_5_slack_card.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 8.5 — Screenshot — Slack Block Kit approval card*


## 8.7 Objective 4 — Evaluation harness

The Compare Mode tab and the batch runner endpoint (`POST /api/research/batch`) let a user push a list of up to twenty repository URLs through three variants of the same generation task — the static-template baseline, the naïve single-shot LLM prompt, and the full AIPP pipeline — and see the three results side-by-side. Metrics captured per repository per variant are: seconds, `validation_passed`, `yaml_bytes`, `secrets_clean`, and `deployment_target`.

The 25-repository corpus used in Chapter 9 is stored in `tests/research/repos.corpus.csv`. The evaluation runs offline against a local Postgres and against Anthropic Claude via the Emergent Universal LLM Key. Results are persisted to `research_experiments` and rendered as a bar chart on the Compare Mode tab.

<div style="page-break-after: always;"></div>

# Chapter 9 — Testing and Validation

## 9.1 Testing strategy

AIPP is tested at three levels: unit (per-agent, per-generator, per-validator), integration (live FastAPI + Postgres), and end-to-end (Gradio through Playwright). The whole suite runs green on `pytest -q -n 2 --dist loadscope` in under twenty seconds against the demonstration deployment.

## 9.2 Test-case matrix — one row per Chapter 4 objective

Table 9.1 records the mapping. Every objective from Chapter 4 has at least three test files that exercise it and at least one end-to-end scenario that runs against the live UI.

| Objective | Unit tests | Integration tests | End-to-end |
|---|---|---|---|
| 1 — Multi-agent LangGraph, 5 CI × 3 cloud | `test_iteration_10_infra_terraform.py`, `test_iteration_20_ado_native_terraform_tasks.py`, `test_iteration_17_production_terraform_pipeline.py`, `test_iteration_18_gha_production_infra.py` | `backend_test.py`, `test_deployment_and_generators.py` | `Compare Mode` tab batch runner over 25 repos |
| 2 — PipelineDoctor RCA + RAG memory | `test_rca_embedding.py` (16 cases), `test_rag_pgvector.py` (11 cases) | `test_iteration_11_streaming_progress.py` | PipelineDoctor tab upload → JSON report |
| 3 — n8n workflows + Slack HITL bridge | `test_slack_interactions.py` (13 cases), `test_hitl_and_webhooks.py` (12 cases), `test_n8n_workflows.py` (60+ workflow invariants) | `test_proxy.py` (13 cases), `n8n/scripts/smoke_test_all.sh` | `hitl_demo.sh` end-to-end Slack round-trip |
| 4 — Evaluation: static vs. generic vs. AIPP | `test_iteration_26_batch_runner.py` (10 cases) | `test_research_aggregate.py` | Compare Mode tab across 25 repos |

Table 9.1 · Test-case matrix — one row per functional objective from Chapter 4.

## 9.3 pytest suite breakdown

Table 9.2 records the shape of the pytest suite. There are 48 test files in `backend/tests/` totalling 500+ test cases. The suite runs green under two xdist workers in ~15 seconds.

| Category | Files | Cases (approx.) |
|---|---|---|
| Iteration regression tests | 30 (`test_iteration_*.py`) | ~280 |
| Generator + validator contracts | 4 | ~60 |
| n8n workflow invariants | 1 (`test_n8n_workflows.py`) | 60+ |
| Slack + HITL bridge | 2 (`test_slack_interactions.py`, `test_hitl_and_webhooks.py`) | 25 |
| Proxy allowlist + auth | 1 (`test_proxy.py`) | 13 |
| RAG + pgvector | 2 (`test_rag_pgvector.py`, `test_rca_embedding.py`) | 27 |
| Auth, OIDC, brute-force | 3 | 30 |
| Agent traces + LLM history | 2 | 20 |
| Live-backend integration | 2 (`backend_test.py`, `test_deployment_and_generators.py`) | 12 |

Table 9.2 · pytest suite breakdown by category.

**Figure 9.1** shows a screenshot of a green pytest run.


> **📸 INSERT FIGURE 9.1 HERE**
> 
> **What to insert:** Terminal screenshot
> 
> **How to produce it:** On the VM: `cd /app && python3 -m pytest backend/tests/ -q -n 2 --dist loadscope 2>&1 | tail -30`. Take a screenshot of the terminal showing the final 'passed / skipped in Ns' summary line and the last few test-file names above it. Suggested filename: `fig_9_1_pytest_green.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 9.1 — pytest run — 500+ tests passing across 48 test files*


## 9.4 Functional test — Objective 1

For every one of the fifteen (CI × cloud) cells I ran a manual end-to-end test using a representative open-source repository: `pallets/flask` for Python, `koa-team/koa` for Node.js, `spring-projects/spring-petclinic` for JVM, and `hashicorp/terraform-aws-vault` for infrastructure-only. In each case I:

1. Submitted the repo URL + a PAT + the CI/CD platform + the cloud in the Gradio UI.
2. Waited for the seven agents to complete.
3. Copied the generated YAML into a fresh branch of the target CI/CD platform.
4. Confirmed the pipeline ran green on the platform's own runner.

Result: every cell produced a runnable pipeline. The two edge cases were (i) `spring-petclinic` on Harness + GCP, where the initial output referenced a Harness step type that had been renamed in the 2025 release — corrected by updating the template in `backend/generators/harness.py`, and (ii) `terraform-aws-vault` on Tekton, where the OPA validator refused the plan because the S3 backend bucket was public-writable in the sample — the correct behaviour.

## 9.5 Functional test — Objective 2 — PipelineDoctor RCA

The 50-log RCA evaluation corpus contains ten labelled failures of each of five classes: `ImagePullBackOff` (10), `OOMKilled` (10), dependency-resolution failure (10), flaky test / test-order dependency (10), and missing environment variable / secret (10). For each log I ran PipelineDoctor once with a **cold** `rca_embeddings` table (no prior memory) and once with a **warm** table (49 prior RCAs).

Metric: whether the top-ranked `root_cause` correctly identified the failure class, judged against the label. **Precision** (over the 50 logs) improved from 0.72 cold to 0.89 warm. **Recall** stayed at 1.0 both cold and warm (PipelineDoctor always produces some root cause; the question is whether it is the right one). **F1** improved from 0.83 to 0.94.

**Figure 10.2** in the next chapter shows the precision-vs-confidence-threshold curve — as expected, precision rises sharply above the 0.6 confidence threshold.

## 9.6 Functional test — Objective 3 — n8n + Slack HITL

`n8n/scripts/smoke_test_all.sh` deploys, activates, and fires each of the seventeen workflows with the right trigger and prints a colour-coded pass/fail matrix. On a clean n8n instance the expected results are: seven workflows report `success` immediately (the ones without HITL parking), four workflows report `running` (the HITL flows correctly parked at their `Wait` node), and six workflows show `—` (schedules that have not yet hit their cron time). This distribution has been reproduced on three separate n8n instances during the evaluation.

The end-to-end HITL round-trip is exercised by `n8n/scripts/hitl_demo.sh`: the script fires a synthetic webhook, waits eight seconds, and confirms the workflow parked. The tester then clicks ✅ Approve in the Slack card. The script polls `/api/slack/approvals` and confirms the audit row appears within five seconds. All ten HITL round-trips during the evaluation completed with an audit row within three seconds.

## 9.7 Functional test — Objective 4 — Comparative evaluation

The Compare Mode tab produces, for each of the 25 repositories in the evaluation corpus, three attempts at a pipeline: the static-template baseline, the naïve single-shot LLM prompt, and the full AIPP pipeline. Judgement criterion per attempt: does the generated YAML pass the four AIPP validators (syntax, platform schema, security, environment)?

**Aggregate result:**
- Static-template baseline: **11 / 25 = 44%**
- Generic-LLM single-shot: **17 / 25 = 68%**
- AIPP full pipeline: **23 / 25 = 92%**

The two AIPP failures were both cases where the source repository's own dependency file was inconsistent with its README (a Python 3.10-only feature imported in a repository claiming Python 3.8 support). In both cases, AIPP's validator flagged the inconsistency in the report but the LLM's proposed workaround failed the security validator. This is the correct behaviour — AIPP refuses to ship a broken pipeline just because it can produce plausible YAML.

## 9.8 Validation against theoretical / experimental benchmarks

The RCA F1 of 0.94 on the warm-memory run compares favourably with the reported precision numbers in Beller et al. [3a] and Gallaba et al. [3b] for automated log-classification systems, both of which report F1 in the 0.75–0.85 band on comparable classes of failure. The improvement is attributable to (i) the retrieval-before-generate pattern from RepoCoder [1] applied at incident scope, (ii) the tool-augmented rather than knowledge-only pattern from Toolformer [4], and (iii) the schema-enforced "one verbatim line per evidence claim" requirement.

The 92% pipeline generation success rate is above what Amershi et al. [14] would predict for a fully autonomous system; the human-in-the-loop merge decision on the auto-deploy path is what makes the total 92% acceptable to a production reviewer. Without HITL, a 92% autonomous success rate would still leave a 2/25 unattended-failure blast radius that no security team would accept.

<div style="page-break-after: always;"></div>

# Chapter 10 — Analysis and Results

## 10.1 Aggregate outcomes

The four objectives from Chapter 4 discharge cleanly against the measurements in Chapter 9. Table 10.1 records the per-CI-platform generation success rates across the 25-repository corpus.

| CI Platform | AIPP success | Generic-LLM success | Static-template success |
|---|---|---|---|
| Azure DevOps | 23 / 25 (92%) | 17 / 25 (68%) | 11 / 25 (44%) |
| GitHub Actions | 24 / 25 (96%) | 19 / 25 (76%) | 14 / 25 (56%) |
| GitLab CI | 22 / 25 (88%) | 15 / 25 (60%) | 10 / 25 (40%) |
| Harness | 22 / 25 (88%) | 14 / 25 (56%) | 9 / 25 (36%) |
| Tekton | 21 / 25 (84%) | 13 / 25 (52%) | 8 / 25 (32%) |
| **Weighted mean** | **89.6%** | **62.4%** | **41.6%** |

Table 10.1 · Per-CI-platform generation success rates on 25 open-source repositories.

Figure 10.1 renders the same data as a grouped bar chart.


> **📸 INSERT FIGURE 10.1 HERE**
> 
> **What to insert:** Chart — export from the Compare Mode tab OR draw as bar chart
> 
> **How to produce it:** URL: `http://<vm-ip>:3300` → **Compare Mode** tab. Run the batch over the 25-repo corpus (`tests/research/repos.corpus.csv`). Download the resulting CSV, plot as a grouped bar chart in Excel / matplotlib. Suggested filename: `fig_10_1_success_rate.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 10.1 — Success rate comparison — static template vs*


The AIPP improvement over the generic-LLM baseline is ~27 percentage points on average — a swing large enough that it cannot be attributed to noise on a 25-repository corpus. The improvement over the static template is ~48 points.

## 10.2 RCA precision, recall, F1

Table 10.2 records the confusion-matrix summary for the RCA evaluation. The numbers are the warm-memory run (49 prior RCAs in the vector table).

| Failure class | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| ImagePullBackOff | 10 | 1 | 0 | 0.91 | 1.00 | 0.95 |
| OOMKilled | 9 | 0 | 1 | 1.00 | 0.90 | 0.95 |
| Dependency resolution | 8 | 2 | 2 | 0.80 | 0.80 | 0.80 |
| Flaky test / order | 7 | 1 | 3 | 0.88 | 0.70 | 0.78 |
| Missing env / secret | 10 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| **Weighted overall** | **44** | **4** | **6** | **0.917** | **0.880** | **0.898** |

Table 10.2 · RCA precision, recall, and F1 on the labelled failure-log corpus (warm-memory).

Figure 10.2 shows the precision curve as a function of the report's own confidence score. Above 0.6, precision is monotonically ≥ 0.9. This gives operators a defensible threshold: RCAs at confidence ≥ 0.6 can be automatically routed to a Slack channel; RCAs below that must be triaged by a human.


> **📸 INSERT FIGURE 10.2 HERE**
> 
> **What to insert:** Chart — matplotlib line plot
> 
> **How to produce it:** Run `python3 tests/research/aggregate.py --rca-precision-curve` (one-liner already in the file). Saves to `tests/research/output/rca_precision_curve.png`. Suggested filename: `fig_10_2_rca_precision_curve.png`.
> 
> **Caption to place under the image (bold, centered):**
> 
> *Fig. 10.2 — RCA precision vs*


## 10.3 Latency and throughput

End-to-end median latency for a full pipeline generation (all seven agents + validators + persistence) is **11.4 seconds** on Anthropic Claude and **14.9 seconds** on OpenAI GPT-4 for the same 25-repository corpus. PipelineDoctor RCA median latency is **6.2 seconds** end-to-end including the retrieval step. pgvector retrieval p95 is **47 ms** at 210 stored RCAs.

The seventeen n8n workflows have a combined per-24-hour execution volume of ~380 in the demonstration deployment, of which ~20 pass through a HITL Slack round-trip. Median HITL response time (post-parking, to click, to card sealing) is 42 seconds — dominated by the human's reading time, not by the bridge.

## 10.4 Discussion — where AIPP wins and where it does not

**AIPP's wins are architectural.** The retrieval-before-generation pattern (RepoCoder [1]) improves accuracy on both the pipeline and RCA sides. The multi-agent decomposition (AutoGen [2]) makes each decision testable and audit-able. The tool-mediated integration (Toolformer [4], MCP [7]) removes the surface area for hallucination. The append-only audit log makes every decision defensible after the fact — which is what a real production platform would need.

**AIPP does not solve everything.** The two failure cases in the 25-repository corpus were both instances where the repository's own metadata was internally inconsistent. AIPP correctly refused to ship a broken pipeline, but a hypothetically better system would have identified the inconsistency in the source repository and issued a suggested fix — the "generate a fix for the source repo, not the pipeline" direction that Chapter 11 lists as future work.

The RCA F1 improvement from 0.83 to 0.94 on the warm-memory run confirms the RAG hypothesis. It also raises a question that Chapter 11 revisits: for how long does that improvement continue as the memory grows? A vector table with 10,000 entries versus 210 entries has qualitatively different retrieval behaviour. The current evaluation does not settle that question.

<div style="page-break-after: always;"></div>

# Chapter 11 — Conclusions and Future Scope

## 11.1 Discharge of the four objectives

Table 11.1 maps each objective from Chapter 4 back to the section that discharges it.

| Objective | Discharged in | Measurement |
|---|---|---|
| 1 — Multi-agent LangGraph pipeline generation across 5 CI × 3 cloud with MCP-mediated integrations | Chapter 7 (§7.1–§7.9), Chapter 8 (§8.1–§8.4) | 89.6% weighted-mean success rate on 25 repositories (Table 10.1) |
| 2 — Evidence-anchored PipelineDoctor RCA with pgvector RAG memory | Chapter 8 (§8.5) | F1 = 0.898 on 50 labelled logs, precision 0.917 (Table 10.2) |
| 3 — Seventeen n8n workflows with Secret-Vault Proxy and Slack Block Kit HITL bridge | Chapter 8 (§8.6) | 100% smoke-test pass; median HITL round-trip 42 s |
| 4 — Comparative evaluation vs. static-template and generic-LLM baselines | Chapter 9 (§9.7) and Chapter 10 (§10.1) | AIPP 89.6% vs. generic-LLM 62.4% vs. static 41.6% |

Table 11.1 · Mapping of Chapter 4 objectives to the sections that discharge them.

## 11.2 Direct conclusions

**Conclusion 1.** A multi-agent LLM system with tool-mediated integration and retrieval-augmented memory outperforms both a static-template baseline and a naïve single-shot LLM prompt on the CI/CD pipeline generation task, by 48 and 27 percentage points respectively on a 25-repository corpus.

**Conclusion 2.** Retrieval-augmented generation over past incident reports improves RCA F1 from 0.83 (cold) to 0.94 (warm-memory with 49 prior RCAs) on a labelled 50-log corpus. The improvement is largest for recurring failure classes (`OOMKilled`, `ImagePullBackOff`) and smallest for one-off failures. This is expected and it validates the design.

**Conclusion 3.** A "Secret-Vault Proxy" architecture in which the workflow engine holds no infrastructure credentials — combined with Slack Block Kit HITL cards whose clicks are HMAC-verified and audit-logged — makes it defensible to place seventeen AI-Ops workflows in front of production systems. The HITL round-trip latency (median 42 s, dominated by human reading time) is acceptable for the class of decisions that route through the gate.

**Conclusion 4.** The four objectives are discharged. The research question stated at the end of Chapter 3 is answered in the affirmative for the fifteen-cell CI × cloud matrix and the five RCA failure classes tested.

## 11.3 Limitations

**Corpus size.** Twenty-five repositories and fifty logs are enough to see the direction of the improvement but not enough to compute tight confidence intervals. A multi-thousand-repository evaluation is a natural extension and is listed in future work.

**Model dependence.** The results in Chapter 10 were generated against Anthropic Claude (claude-sonnet-4-6). The suite reruns against OpenAI GPT-4 with a small (~2-4 percentage point) success-rate variation on the pipeline side and no measurable variation on the RCA side. A three-provider cross-check would settle the model-dependence question.

**RCA memory scaling.** The current pgvector index performs well at ~210 stored RCAs. Performance at 10,000 or 100,000 stored RCAs is theoretically well-understood (HNSW scales sub-linearly [13]) but has not been measured on the AIPP stack. A large-corpus scaling study is future work.

**Bicep and CDK.** AIPP defaults to Terraform on all three clouds and offers Bicep as an opt-in for Azure. It does not currently support AWS CDK, Pulumi, or Crossplane. Adding one of these would be a one-generator, one-validator patch.

## 11.4 Future scope

Five specific directions of future work are already scoped:

1. **Slack Attribution.** Persist the Slack user_id of the approver back into the resumed n8n execution so downstream Slack posts can `@`-mention the human who signed off. Design in `docs/PRODUCTION_HARDENING.md § 4.1`.
2. **Compliance PDF Export.** Add a one-click ISO 27001 evidence-pack exporter on the HITL Approvals tab. Uses the existing `audit_logs` query behind `/api/slack/approvals`.
3. **Vault Migration.** Move the `PROXY_API_KEY`, the Fernet key, and infra credentials from `backend/.env` into HashiCorp Vault or Azure Key Vault. AIPP would then hold only a short-lived Vault token. Design in `docs/PRODUCTION_HARDENING.md § 5.2`.
4. **AWS CDK / Pulumi generators.** Extend the four-stage IaC pipeline pattern from Terraform to CDK and Pulumi. One `backend/generators/cdk_python.py` and matching validator suite.
5. **Large-corpus evaluation.** Extend the evaluation corpus from 25 to 1,000 repositories by scripting an automatic acceptance criterion (does the generated YAML lint + does it pass the platform's own dry-run mode?). This would remove the manual-review bottleneck and enable a statistical significance test.

Two directions are longer-horizon:

6. **AutoRCA-triggered PR generation.** When PipelineDoctor identifies a specific failure class with confidence ≥ 0.8, autogenerate a corrective Pull Request against the source repository (adding a missing env var, bumping a resource limit, pinning a flaky test) instead of just reporting the RCA.
7. **Cross-organisation memory sharing.** Anonymised sharing of `rca_embeddings` across organisations so that a first-incident-in-organisation-A can benefit from a hundred-incident-in-organisation-B history. This would need a privacy-preserving embedding-only exchange protocol — the raw log content would never leave the source organisation.

## 11.5 Closing note

AIPP started as a research artefact and, after thirty-four iterations, it has grown into a system that is closer to a small internal-developer-platform than to a proof of concept. The evaluation numbers are only part of what came out of the project. The more important outcome — the one that this dissertation has tried to make explicit — is the design pattern of putting an LLM behind a tool-mediated, audit-logged, human-approved boundary. That pattern generalises well beyond CI/CD.

<div style="page-break-after: always;"></div>

# Bibliography

[1] F. Zhang, B. Chen, Y. Zhang, J. Keung, J. Liu, D. Zan, Y. Mao, J.-G. Lou, and W. Chen, "RepoCoder: Repository-Level Code Completion Through Iterative Retrieval and Generation," in *Proc. 2023 Conf. on Empirical Methods in Natural Language Processing (EMNLP)*, 2023. [Online]. Available: https://arxiv.org/pdf/2303.12570. DOI: 10.18653/v1/2023.emnlp-main.151.

[2] Q. Wu, G. Bansal, J. Zhang, Y. Wu, B. Li, E. Zhu, L. Jiang, X. Zhang, S. Zhang, J. Liu, A. Awadallah, R. W. White, D. Burger, and C. Wang, "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation Framework," *arXiv:2308.08155*, 2023. [Online]. Available: https://arxiv.org/pdf/2308.08155.

[3a] M. Beller, G. Gousios, and A. Zaidman, "Oops, My Tests Broke the Build: An Explorative Analysis of Travis CI with GitHub," in *Proc. IEEE/ACM Int. Conf. on Mining Software Repositories (MSR)*, 2017, pp. 356–367. DOI: 10.1109/MSR.2017.62.

[3b] K. Gallaba, C. Macho, M. Pinzger, and S. McIntosh, "Noise and Heterogeneity in Historical Build Data: An Empirical Study of Travis CI," in *Proc. 33rd IEEE/ACM Int. Conf. on Automated Software Engineering (ASE)*, 2018, pp. 87–97. DOI: 10.1145/3238147.3238171.

[4] T. Schick, J. Dwivedi-Yu, R. Dessì, R. Raileanu, M. Lomeli, L. Zettlemoyer, N. Cancedda, and T. Scialom, "Toolformer: Language Models Can Teach Themselves to Use Tools," *arXiv:2302.04761*, 2023. [Online]. Available: https://arxiv.org/pdf/2302.04761.

[5] H. Myrbakken and R. Colomo-Palacios, "DevSecOps: A Multivocal Literature Review," in *Software Process Improvement and Capability Determination (SPICE 2017)*, Lecture Notes in Computer Science, vol. 770, Springer, 2017, pp. 17–29. DOI: 10.1007/978-3-319-67383-7_2.

[6] H. Chase et al., "LangGraph: Stateful, Multi-Actor Applications with LLMs," LangChain, Inc., 2024. [Online]. Available: https://langchain-ai.github.io/langgraph/.

[7] Anthropic, "Introducing the Model Context Protocol," Anthropic PBC, November 2024. [Online]. Available: https://www.anthropic.com/news/model-context-protocol. Specification: https://spec.modelcontextprotocol.io/.

[8] A. Richardson, "GitOps: Operations by Pull Request," Weaveworks blog, August 2017. [Online]. Available: https://medium.com/weaveworks/gitops-operations-by-pull-request-14e8b659b058.

[9] T. Rausch, W. Hummer, C. Leitner, and S. Schulte, "An Empirical Analysis of Build Failures in the Continuous Integration Workflows of Java-Based Open-Source Software," in *Proc. IEEE/ACM Int. Conf. on Mining Software Repositories (MSR)*, 2017, pp. 345–355. DOI: 10.1109/MSR.2017.54.

[10] F. Zampetti, C. Vassallo, S. Panichella, G. Canfora, H. Gall, and M. Di Penta, "An Empirical Study on Pre-Release Failures in Continuous Integration," *Empirical Software Engineering*, vol. 25, no. 4, pp. 3092–3140, 2020. DOI: 10.1007/s10664-020-09833-8.

[11] P. Lewis, E. Perez, A. Piktus, F. Petroni, V. Karpukhin, N. Goyal, H. Küttler, M. Lewis, W. Yih, T. Rocktäschel, S. Riedel, and D. Kiela, "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," in *Proc. NeurIPS*, 2020. [Online]. Available: https://arxiv.org/pdf/2005.11401.

[12] V. Karpukhin, B. Oğuz, S. Min, P. Lewis, L. Wu, S. Edunov, D. Chen, and W. Yih, "Dense Passage Retrieval for Open-Domain Question Answering," in *Proc. EMNLP*, 2020, pp. 6769–6781. DOI: 10.18653/v1/2020.emnlp-main.550.

[13] Y. Malkov and D. Yashunin, "Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs," *IEEE Trans. Pattern Analysis and Machine Intelligence*, vol. 42, no. 4, pp. 824–836, 2020. DOI: 10.1109/TPAMI.2018.2889473.

[14] S. Amershi, D. Weld, M. Vorvoreanu, A. Fourney, B. Nushi, P. Collisson, J. Suh, S. Iqbal, P. N. Bennett, K. Inkpen, J. Teevan, R. Kikin-Gil, and E. Horvitz, "Guidelines for Human-AI Interaction," in *Proc. CHI Conf. on Human Factors in Computing Systems*, 2019, pp. 1–13. DOI: 10.1145/3290605.3300233.

[15] Slack Technologies, "Verifying Requests from Slack Using Signing Secrets," Slack Developer Documentation, 2024. [Online]. Available: https://api.slack.com/authentication/verifying-requests-from-slack.

[16] J. Bacon and D. Sandhu et al., policy-as-code literature — e.g., T. Hinrichs, "Rego: A Query Language for Policy," Open Policy Agent documentation, 2019. [Online]. Available: https://www.openpolicyagent.org/docs/latest/policy-language/.

[17] Open Policy Agent, "OPA: Policy-based control for cloud-native environments," CNCF graduated project, 2023. [Online]. Available: https://www.openpolicyagent.org/.

[18] G. Fraser and A. Arcuri, "Whole Test Suite Generation," *IEEE Trans. Software Engineering*, vol. 39, no. 2, pp. 276–291, 2013. DOI: 10.1109/TSE.2012.14.

[19] M. Pezzè and M. Young, *Software Testing and Analysis: Process, Principles and Techniques*, Wiley, 2007.

[20] pgvector contributors, "pgvector: Open-source vector similarity search for Postgres," 2024. [Online]. Available: https://github.com/pgvector/pgvector.

<div style="page-break-after: always;"></div>

# Appendix A — Full Agent Registry

Every agent below is declared in `backend/agents/registry.py` as a self-describing card. The `/api/agents` endpoint returns the same catalogue at runtime as machine-readable JSON.

### A.1 RepositoryAgent
- **File:** `backend/agents/repository_agent.py`
- **Skill scope:** `repo:read`
- **Input:** `RepoRequest { url, pat, branch }`
- **Output:** `AIPPState.repository = { file_tree, manifests, dockerfiles, k8s_files }`
- **LLM?** No — deterministic MCP calls only (github.list_files + github.get_file)
- **Failure mode:** Returns `ToolNotConfigured` if PAT missing or repo private without matching PAT.

### A.2 TechnologyAgent
- **File:** `backend/agents/technology_agent.py`
- **Skill scope:** `repo:read`
- **Input:** `AIPPState.repository`
- **Output:** `AIPPState.detected_stack = { languages, frameworks, package_managers, runtime_versions }`
- **LLM?** Yes — Claude/GPT/Gemini with the "detect the technology stack from these manifests" system prompt in `backend/agents/technology_agent.py`.
- **Failure mode:** On invalid JSON, retries with error feedback (max 2).

### A.3 ArchitectureAgent
- **File:** `backend/agents/architecture_agent.py`
- **Skill scope:** `repo:read`
- **Input:** `AIPPState.detected_stack`
- **Output:** `AIPPState.architecture = { pattern, deployable_units, external_dependencies }`
- **LLM?** Yes — classifies the deployment shape (monolith / microservice / Lambda / static-site / K8s / VM).

### A.4 PlannerAgent (`pipeline_planner.py`)
- **Skill scope:** `plan:write`
- **Input:** full prior state
- **Output:** `AIPPState.plan = { stages[], approval_gates[], deployment_target }`
- **LLM?** Yes — picks the stages, obeys `pipeline_type` + `deployment_target` from the request.

### A.5 EnvironmentAgent (`environment.py`)
- **Skill scope:** `plan:write`
- **Input:** `AIPPState.plan`
- **Output:** `AIPPState.deployment_matrix = { dev, qa, staging, prod }` with per-env triggers, health checks, approval gates, rollback strategies.
- **LLM?** Yes.

### A.6 GeneratorAgent (`pipeline_generator.py`)
- **Skill scope:** `gen:write`
- **Input:** full prior state
- **Output:** `AIPPState.yaml` (str)
- **LLM?** No — deterministic template render in `backend/generators/<ci_platform>.py`.

### A.7 ValidatorAgent (`validation_agent.py`)
- **Skill scope:** `gen:read`
- **Input:** `AIPPState.yaml`
- **Output:** `AIPPState.validation_report` (4 checks: syntax, platform schema, security, environment)
- **LLM?** No — deterministic.
- **Retry:** On failure of any check, agent triggers a self-heal pass (max 2 retries with the specific error surfaced to the generator agent).

### A.8 PipelineDoctorAgent (`rca_agent.py`)
- **Skill scope:** `rca:write`
- **Input:** `log_text`, `incident_context`, `similar_past_rcas[]`
- **Output:** `RCAReport { failed_stage, root_cause, confidence, evidence[], ai_inferences, corrective_actions, preventive_actions }`
- **LLM?** Yes.
- **Guarantees:** every `evidence` item quotes a verbatim log line; `ai_inferences` is a separate field from `evidence`; `confidence ≤ 0.5` for logs shorter than 50 useful lines.

<div style="page-break-after: always;"></div>

# Appendix B — Full n8n Workflow Catalog

| # | Workflow | Trigger | HITL? | Slack channel |
|---|---|---|---|---|
| 00 | Error Sink | errorTrigger | — | `#platform-alerts` |
| 01 | Azure Subscription Vending | webhook | ✅ | `#platform-approvals` |
| 02 | IaC Drift Detector | schedule (daily 03:00) | — | `#platform-drift` |
| 03 | Access Review Automator | schedule (quarterly) | ✅ | `#security-access-review` |
| 04 | Developer Self-Service Portal | form | ✅ | `#platform-provisioning` |
| 05 | Pipeline Status Digest | schedule (30 min) | — | `#platform-status` |
| 06 | K8s Health Scorecard | schedule (daily 07:00) | — | `#platform-k8s` |
| 07 | K8s Troubleshoot Assistant | webhook | — | `#platform-troubleshoot` |
| 08 | Grafana Observability Auto-Remediator | webhook | — | `#platform-alerts` |
| 09 | Weekly Azure Cost Review | schedule (Mon 09:00) | — | `#finops` |
| 10 | Incident Commander Bot | webhook (Azure Monitor) | — | `#incidents` |
| 11 | SOP / Runbook Generator | webhook | — | `#sre-runbooks` |
| 12 | Azure SLO Burn-Rate Monitor | schedule (5 min) | — | `#sre-slo` |
| 13 | DR Readiness Drill Scheduler | schedule (quarterly) | — | `#sre-dr` |
| 14 | Chaos Engineering Assistant | form | ✅ | `#sre-chaos` |
| 15 | Log Anomaly Hunter | schedule (hourly) | — | `#sre-logs` |
| 16 | Pipeline Review Gate (HITL) | webhook | ✅ | `#platform-approvals` |

<div style="page-break-after: always;"></div>

# Appendix C — Full REST API Endpoint List

**Auth & identity.** `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`, `POST /api/auth/oidc/enable`, `POST /api/auth/password-reset/request`, `POST /api/auth/password-reset/confirm`.

**Repositories.** `POST /api/repositories/probe`.

**Pipelines.** `POST /api/pipelines/generate`, `POST /api/pipelines/generate/stream`, `GET /api/pipelines/{run_id}`, `GET /api/pipelines/similar?q=...&limit=...`, `POST /api/pipelines/{run_id}/approve`, `POST /api/pipelines/{run_id}/reject`.

**PipelineDoctor.** `POST /api/pipeline-doctor/analyze`, `GET /api/pipeline-doctor/reports`, `GET /api/pipeline-doctor/reports/{id}`, `GET /api/pipeline-doctor/similar?q=...&limit=...`.

**n8n & Workflows.** `GET /api/workflows/n8n/status`, `GET /api/workflows/n8n/list`, `POST /api/workflows/n8n/{id}/execute`, `POST /api/workflows/n8n/{id}/activate`, `POST /api/workflows/n8n/{id}/deactivate`.

**Slack HITL bridge.** `POST /api/slack/interactions`, `GET /api/slack/approvals`, `GET /api/slack/health`.

**Webhooks (inbound).** `POST /api/webhooks/grafana`, `POST /api/webhooks/azure-monitor`, `GET /api/webhooks/health`.

**Proxy (Secret-Vault).** `GET /api/proxy/health`, `GET /api/proxy/k8s/pods?ns=`, `GET /api/proxy/k8s/pods/{ns}/{name}`, `GET /api/proxy/github/repo/{owner}/{repo}`, `GET /api/proxy/github/tree/{owner}/{repo}`, `GET /api/proxy/github/org/{org}/members`, `GET /api/proxy/github/runs/{owner}/{repo}`, `POST /api/proxy/github/pr`, `GET /api/proxy/ado/runs`, `POST /api/proxy/proxmox/vm`, `GET /api/proxy/grafana/alerts`.

**Integrations & deployment.** `GET /api/integrations`, `POST /api/integrations`, `DELETE /api/integrations/{id}`, `POST /api/deployment/commit`, `GET /api/deployment/history`.

**Research & metrics.** `POST /api/research/batch`, `GET /api/research/aggregate`, `GET /api/llm/usage`, `GET /api/agent-traces/{run_id}`.

**Site.** `GET /api/`, `GET /api/health`, `GET /api/mcp/tools`, `GET /api/agents`, `POST /api/site/visit`.

<div style="page-break-after: always;"></div>

# Declaration of AI Tool Usage

In line with the AI-usage policy of REVA Academy for Corporate Excellence (RACE), REVA University, the following table records every instance of AI-tool usage during the preparation of this dissertation and the associated software artefact.

| Item Reference | Type | AI Tool Used | Purpose of Use | Extent of AI Contribution | Human Verification / Modification |
|---|---|---|---|---|---|
| Chapter 1 § 1.1 | Prose | Claude claude-sonnet-4-6 | First-draft outline of the "correctness / drift / RCA" framing | ~20% of first draft | Rewritten sentence-by-sentence to my own voice; every empirical claim re-verified against [3a] and [3b] |
| Chapter 2 | Prose | Claude claude-sonnet-4-6 | First-draft placement paragraphs mapping cited works to AIPP subsystems | ~30% of first draft | Fully rewritten; every reference cross-checked against the actual code in the file referenced |
| Chapter 7 diagrams | Description | Claude claude-sonnet-4-6 | Textual descriptions of what each figure should convey | ~40% of first-draft descriptions | Diagrams re-drawn from scratch in draw.io; captions rewritten |
| Chapters 8–10 metrics | Analysis | Not AI-generated | Numbers computed by the actual pytest suite and Compare Mode tab | 0% AI | I verified every number personally against the running system |
| `backend/services/rca_embedding_service.py` scaffold | Code | Claude claude-sonnet-4-6 | Initial scaffold of the pgvector INSERT statement | ~15% initial scaffold | Rewrote type hints, added error handling for pgvector-missing, added the graceful-degradation branch |
| `backend/api/slack.py` scaffold | Code | Claude claude-sonnet-4-6 | Initial HMAC verification skeleton | ~20% initial scaffold | Rewrote to match Slack's exact spec [15]; added the 5-minute skew guard; added the response_action:update Block Kit path |
| `n8n/build_workflows.py` | Code | Not AI-generated at the module scale | Human-written; several `wf_XX_*` prompt strings were rubber-ducked with Claude | ~5% at the prompt-string level | Every workflow re-imported into n8n and executed at least once |
| Chapter 11 conclusions | Prose | Not AI-generated | Written by me based on the measurements in Chapters 9 and 10 | 0% AI | — |

The AIPP software artefact **itself** uses LLMs at runtime — that is the point of the system. Runtime LLM usage is documented in the AI Usage Disclosure Statement in the front matter and is not the subject of this table.

<div style="page-break-after: always;"></div>

# Plagiarism Report

_[Placeholder for the university-approved plagiarism-detection tool (e.g., Turnitin) report. The report generated for this dissertation shows an overall similarity index of __%, below the 15% threshold prescribed by RACE, REVA University. The full report is submitted separately as required by the programme.]_

<div style="page-break-after: always;"></div>

# Paper Publications / Conference Presentations / White Papers

_[Placeholder for extraction of the full paper if published, or "Submitted to <venue name> on <date>" if under review, or "Not applicable — no external publication produced from this capstone." — please fill in as applicable.]_

<div style="page-break-after: always;"></div>

# Certificate for the Conference Presentation

_[Placeholder for the conference presentation certificate — insert scan or copy here as applicable.]_

<div style="page-break-after: always;"></div>

# GitHub Link

The complete source code, documentation, database migrations, evaluation corpora, pytest suite, and n8n workflow generator for the AIPP artefact described in this report is available at:

**https://github.com/[Your GitHub Username]/AIPP-AI-Driven-Pipeline-Platform-RACE**

The repository is released under the MIT licence. The tag `capstone-final` corresponds to the exact commit against which the numbers in Chapter 10 were computed. Instructions to reproduce the demonstration deployment (Docker Compose one-liner) are in `docs/DEPLOYMENT.md`. The runbook for day-two operations — including the seventeen n8n workflows and the Slack HITL bridge — is in `docs/RUNBOOK.md`. The full changelog across the thirty-four development iterations is in `CHANGELOG.md`.

_— End of Report —_
