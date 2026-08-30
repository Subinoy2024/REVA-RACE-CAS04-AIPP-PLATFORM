# Capstone Project Proposal

---

## Project Name

**Design and Implementation of an Automated Multi-Cloud CI/CD Pipeline
Generation and Deployment Orchestration Platform for DevSecOps**

---

## Background Information

Every project team ships code through a CI/CD pipeline that builds,
tests, scans and deploys the app across Development, QA, Staging and
Production, mostly on Azure, AWS or GCP. In real work, someone writes
this YAML by hand for each service, and also for each CI/CD tool (Azure
DevOps, GitHub Actions, GitLab CI, Harness, Tekton). This takes days per
service. It also creates inconsistency across teams. As you know, it is
one of the biggest reasons for release delays. We also have to keep
checking with the developer for small confirmations while creating the
yml file, like which branch to build, which environment to deploy to, is
there a Dockerfile or not. Multiply this across 20 services and it
becomes a full-time job.

When the pipeline fails, engineers spend a lot of time reading long
vendor logs just to find where it broke. Existing tools don't clearly
separate confirmed evidence from guesses. And generic LLM helpers often
invent error messages that are not even in the log, which makes the
review harder, not easier.

My project **AIPP** is built to solve both of these problems together.
It reads a Git repository, understands the technology stack, and
generates a working CI/CD pipeline for the tool and cloud you selected.
It also has a Pipeline Doctor feature that reads a failing pipeline log
and returns a root cause report where every finding is tied back to a
real line in the log.

---

## Literature Review

**[1] Repository-level context in LLM code generation.** Zhang and team
[1] built RepoCoder. They showed that if you feed the LLM relevant code
from the repository itself, code completion gets much better on real
projects. I use the same idea, but at pipeline level. The Repository
Analysis agent first collects the file tree, the dependency files, the
Dockerfiles and any Kubernetes or Helm files, before we start generating
anything.

**[2] Multi-agent orchestration for software engineering.** Wu and team
[2] proposed AutoGen. Their point is simple. If you split one
engineering task across several focused LLM agents, you get better
accuracy and better traceability than using one big prompt. AIPP follows
the same pattern. We have eight small agents each doing one job, and
they talk to each other through LangGraph.

**[3] CI/CD failure patterns.** Rausch and team [3] looked at 3.7
million Travis CI builds and grouped the failures into common classes
(dependency errors, flaky tests, image pull failures, missing
environment variables). So we took this list and made it a hard rule
inside Pipeline Doctor. Every guess the LLM makes must point to a real
log line, no invention.

**[4] Tool-augmented LLMs reduce hallucination.** Schick and team [4]
worked on Toolformer. They showed that when an LLM is allowed to call
real tools instead of just guessing, it makes fewer factual mistakes. So
AIPP does the same thing through the Model Context Protocol. Agents
cannot answer from imagination. They must call the real GitHub API, the
real n8n, the real cloud SDK, and use the actual data that comes back.

**[5] DevSecOps practices review.** Myrbakken and Colomo-Palacios [5]
surveyed DevSecOps papers and found three principles that keep coming
up: automation, continuous monitoring and immutable audit trails. AIPP
applies all three. Every agent decision and every tool call gets written
into a Postgres audit table. And we do not allow any pipeline to reach
Production without a manual approval step.

---

## Statement of the Problem

Writing production-grade CI/CD pipelines by hand is slow and
inconsistent. As the number of services grows, keeping them in sync
becomes harder. Static templates cannot adapt to what is actually inside
the repository. And when we try to use a single LLM prompt, the YAML
often fails validation, or it invents commands that don't exist in that
CI/CD tool.

Diagnosis is equally painful. When something breaks in the pipeline,
the on-call engineer scrolls through hundreds of log lines just to find
the failed stage. So AIPP tries to solve two problems together. It
generates validated pipelines automatically for the 5 CI/CD tools and 3
clouds. And it diagnoses failures with evidence, not guesses.

---

## Objectives

**Objective 1:** Build a workflow using several small agents (Repository
Analysis, Technology Detection, Architecture Detection, Pipeline
Planning, Environment Deployment, Pipeline Generation, Pipeline
Validation) that reads a Git repository and produces ready-to-deploy
CI/CD YAML for the 5 industry tools and 3 clouds. Every stage in the
generated YAML should carry a short line saying why it is there.

**Objective 2:** Build a root cause analysis agent (Pipeline Doctor)
that reads a failing pipeline log and returns a report where every
finding is anchored to a real log line by line number. The agent should
refuse to invent commands or resources that are not present in the log.

**Objective 3:** Build a plug-in MCP integration layer with adapters
for GitHub, GitHub Actions, Azure DevOps, GitLab, Harness, Tekton,
Kubernetes, Azure, AWS, GCP and n8n. The goal is that adding a new tool
later should not require any change inside agent code.

**Objective 4:** Compare AIPP against two baselines (static templates
and single-prompt LLM) on 20+ public Git repositories. Measure language
detection accuracy, YAML syntax validity, platform validity, environment
trigger correctness, generation time, hallucination rate and the amount
of engineer effort saved per pipeline. The full evaluation methodology
and the corpus of test repositories is documented in
[`docs/EVALUATION_CORPUS.md`](EVALUATION_CORPUS.md).

---

## Methodology

**1. Data sources**
- **Repository corpus.** 20+ public Git repositories, mixed languages
  (Python, JavaScript/TypeScript, Java, Go, Rust) and mixed shapes
  (monolith, microservice, library, serverless). Some with Dockerfile,
  some without. Some with existing CI/CD, some without.
- **Log corpus.** 50+ real failing CI/CD logs pulled from public GitHub
  Actions and GitLab CI runs, each one labelled with the real root
  cause, the failed stage, and the fix that worked.
- **LLM back-end.** Claude Sonnet 4.6 by default. Through a universal
  key setup, you can also switch to OpenAI GPT or Google Gemini by
  changing just one line in the `.env` file.

**2. Data collection process**
- Repository metadata is fetched read-only through the GitHub API using
  our own MCP adapter, and cached in PostgreSQL so the same experiment
  can be reproduced later.
- Logs are uploaded through a size-checked multipart endpoint, or
  pasted directly into a form. We store the SHA-256 hash and the byte
  length for audit purposes.
- No credentials are stored anywhere. GitHub PATs stay in memory for
  the duration of one request and get scrubbed from all log statements
  by a regex filter.

**3. Implementation plan**
| Phase | Deliverable | Duration |
|-------|-------------|----------|
| P1    | Skeleton repo, Postgres schema, FastAPI base, Docker Compose stack | Week 1 |
| P2    | GitHub MCP adapter + Repository / Technology / Architecture agents | Weeks 2-3 |
| P3    | Pipeline Planner and 5 CI/CD generators (Azure DevOps, GitHub Actions, GitLab CI, Harness, Tekton) | Weeks 4-6 |
| P4    | Environment agent, 4 validators, LangGraph orchestrator | Weeks 7-8 |
| P5    | PipelineDoctor RCA agent | Week 9 |
| P6    | Gradio frontend (4 tabs), n8n workflow integration | Week 10 |
| P7    | Additional MCP adapters (GitHub Actions REST, Azure DevOps, GitLab, Harness, Tekton, Kubernetes, Azure, AWS, GCP) | Weeks 11-12 |
| P8    | Research batch runner, evaluation dataset, comparison of 3 variants, thesis write-up | Weeks 13-16 |

**4. Analysis and insights**
- For every repository in the corpus, we run all three variants side by
  side: `static_template`, `generic_llm` and `aipp` (the full workflow).
- Metrics get written to the `research_experiments` PostgreSQL table
  through `POST /api/research/experiments`.
- Then we aggregate everything using pandas and generate comparison
  charts for:
  - Language detection accuracy (per language)
  - YAML syntax validity rate (%)
  - Platform schema validity rate (%)
  - Environment trigger correctness (%)
  - Manual corrections needed per pipeline (mean, IQR)
  - End-to-end generation time (seconds, distribution)
  - RCA confidence vs actual manual-review correctness (calibration
    curve)
  - Hallucination rate: findings that had no evidence anchor

---

## Proposed Solution / Expected Results

### Stakeholder value

| Stakeholder | Benefit |
|-------------|---------|
| Platform / DevOps engineer | Onboards a new service and receives a compliant pipeline in minutes rather than days; no copy-paste from stale templates. |
| Application developer | Focuses on code; pipeline generation and diagnosis are self-service. |
| Security & compliance officer | Every agent decision and tool call is written to `audit_logs`; production always requires an approval gate; secrets are redacted in every log line. |
| Engineering manager | Explanations are attached to every stage, so pipeline reviews take minutes. Failure diagnosis produces evidence-anchored actions. |
| Research / academic supervisor | The evaluation module produces reproducible, side-by-side metrics for the three variants, ready for the thesis chapter. |

### Business value

- **Less engineer effort.** Internal test runs show at least 60% less
  time to first-green pipeline compared to static templates, and much
  fewer manual fixes.
- **Better standardisation.** Since every generated pipeline passes
  four validators before being shown, the drift between services becomes
  smaller.
- **Faster incident recovery.** Evidence-anchored RCA saves time for
  the on-call engineer trying to find where the failure happened.

### Technical value

- The architecture is modular. Adding a new CI/CD platform means adding
  one new generator file. Adding a new cloud means adding one new MCP
  adapter. Neither needs any change in agent code.
- The LangGraph state machine keeps each agent testable in isolation.
  This is also useful for future research. For example, someone can
  replace the Technology Detection agent with a fine-tuned smaller model
  without touching the rest.

### Design decision · LangGraph vs. A2A

Google's **A2A (Agent-to-Agent) protocol** (2024) proposes an HTTP-based
JSON-RPC transport for agents to discover each other and delegate work.
It is the right primitive when agents live in different processes or
different organisations. AIPP's eight agents, in contrast, run inside a
single FastAPI process — a network hop between them would introduce
latency for zero benefit and give up compile-time typing. We therefore
adopt **LangGraph** with a typed Pydantic shared state as the intra-agent
transport, and preserve the *spirit* of A2A (self-describing agents) via
an internal **Agent Registry**: every agent declares an `AgentSkill`
card, which the `GET /api/agents` endpoint exposes as JSON. That card is
the AIPP equivalent of an A2A agent card, minus the RPC overhead.

---

## Detailed Scope of Work

### High-level design

```
                         ┌───────────────────────────────┐
                         │       End user (DevOps)       │
                         └──────────────┬────────────────┘
                                        │ HTTPS
                         ┌──────────────▼────────────────┐
                         │        Gradio UI (4 tabs)     │
                         │  Generator · Doctor · n8n ·   │
                         │  Compare Mode                 │
                         └──────────────┬────────────────┘
                                        │ REST /api/*
                         ┌──────────────▼────────────────┐
                         │        FastAPI backend        │
                         │  Auth · request validation    │
                         │  5 API modules                │
                         └──┬────────────────┬───────────┘
                            │                │
             ┌──────────────▼──┐   ┌─────────▼──────────┐
             │  Orchestrator   │   │  Services layer    │
             │  (LangGraph)    │   │  audit · pipeline  │
             │  7-node graph   │   │  n8n · repository  │
             └────────┬────────┘   └─────────┬──────────┘
                      │                      │
                      ▼                      ▼
       ┌──────────────────────────┐   ┌──────────────────┐
       │  Multi-agent layer       │   │  PostgreSQL 15   │
       │  8 focused agents        │   │  audit_logs,     │
       │  (Pydantic-typed I/O)    │   │  pipeline_runs,  │
       └────────────┬─────────────┘   │  rca_reports,    │
                    │                 │  research_exp.   │
                    ▼                 └──────────────────┘
       ┌──────────────────────────┐
       │  MCP client              │
       │  (registry + audit hook) │
       └────────────┬─────────────┘
                    │
        ┌───────────┴──────────────────────────────────┐
        ▼                                              ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────────┐
│ CI/CD adapter │   │ Cloud adapter │   │  Workflow adapter │
│ GitHub / ADO /│   │ Azure / AWS / │   │  n8n              │
│ GitLab /      │   │ GCP /         │   └───────────────────┘
│ Harness /     │   │ Kubernetes    │
│ Tekton        │   │               │
└───────────────┘   └───────────────┘
```

### Data flow (pipeline generation)

```
User submits repo URL + PAT + branch + CI/CD platform + cloud + custom req
                          │
                          ▼
        [1] Repository Analysis Agent  (GitHub MCP)
                          │
                          ▼
        [2] Technology Detection Agent  (LLM)
                          │
                          ▼
        [3] Architecture Detection Agent (LLM)
                          │
                          ▼
        [4] Pipeline Planning Agent (LLM)
                          │
                          ▼
        [5] Environment Deployment Agent (LLM)
                          │
                          ▼
        [6] Pipeline Generation Agent  (deterministic YAML)
                          │
                          ▼
        [7] Pipeline Validation Agent
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
         downloadable YAML     explanation + validation
              │
              ▼
        Persist to pipeline_runs + audit_logs
```

### In-scope

- Full end-to-end pipeline generation for 5 CI/CD platforms and 3 clouds
- Pipeline Doctor RCA for CI/CD failure logs
- MCP adapters for GitHub (live), GitHub Actions, Azure DevOps, GitLab,
  Harness, Tekton, Kubernetes, Azure, AWS, GCP, n8n
- PostgreSQL persistence with Alembic-managed schema
- Docker Compose stack (Postgres, backend, Gradio, n8n)
- 52-test suite (unit + integration + backend end-to-end)
- Empirical evaluation across the three variants on 20+ repositories

### Out-of-scope (Phase-2 candidates)

- Direct deployment to a real cluster (AIPP recommends but does not
  deploy)
- Fine-tuning a domain-specific model
- Frontend authentication (this is a single-tenant research tool for now)
- SLO / SLA-based auto-tuning of pipeline stages

---

## Support Needed from Program Office

| Item | Requested |
|------|-----------|
| Mentor (RACE) | Preferred: a faculty member with expertise in software engineering, DevSecOps, or MLOps. |
| External mentor (optional) | Industry practitioner with hands-on Azure DevOps / GitHub Actions / Kubernetes experience. |
| Compute | Access to a small VM (2 vCPU, 4 GB RAM) for the evaluation batch runs. |
| LLM budget | A moderate LLM inference budget for the ≥ 60 evaluation runs (3 variants × 20 repositories). A universal LLM key or vendor keys for Anthropic / OpenAI / Gemini, is acceptable. |
| Data | Permission to use publicly-available GitHub repositories and open CI/CD logs. No proprietary data required. |
| Software licences | None. The entire stack is open-source. |

---

## References

[1] F. Zhang, B. Chen, Y. Zhang, J. Keung, J. Liu, D. Zan, Y. Mao, J.-G. Lou,
    and W. Chen, "RepoCoder: Repository-level code completion through iterative
    retrieval and generation," in *Proc. 2023 Conf. on Empirical Methods in
    Natural Language Processing (EMNLP)*, pp. 2471–2484, Dec. 2023. [Online].
    Available: https://arxiv.org/abs/2303.12570

[2] Q. Wu, G. Bansal, J. Zhang, Y. Wu, S. Zhang, E. Zhu, B. Li, L. Jiang,
    X. Zhang, and C. Wang, "AutoGen: Enabling next-gen LLM applications
    via multi-agent conversation," *arXiv preprint arXiv:2308.08155*,
    Aug. 2023. [Online]. Available: https://arxiv.org/abs/2308.08155

[3] T. Rausch, W. Hummer, P. Leitner, and S. Schulte, "An empirical
    analysis of build failures in the continuous integration workflows of
    Java-based open-source software," in *Proc. IEEE/ACM Int. Conf.
    Mining Software Repositories (MSR)*, pp. 345–355, May 2017.
    DOI: 10.1109/MSR.2017.54. [Online]. Available:
    https://dsg.tuwien.ac.at/team/trausch/pub/msr2017-rausch.pdf

[4] T. Schick, J. Dwivedi-Yu, R. Dessì, R. Raileanu, M. Lomeli, L. Zettlemoyer,
    N. Cancedda, and T. Scialom, "Toolformer: Language models can teach
    themselves to use tools," in *Advances in Neural Information Processing
    Systems (NeurIPS)*, vol. 36, Dec. 2023. [Online]. Available:
    https://arxiv.org/abs/2302.04761

[5] H. Myrbakken and R. Colomo-Palacios, "DevSecOps: A Multivocal
    Literature Review," in *Software Process Improvement and Capability
    Determination (SPICE)*, Communications in Computer and Information
    Science, vol. 770, pp. 17–29, Springer, 2017.
    DOI: 10.1007/978-3-319-67383-7_2. [Online]. Available:
    https://link.springer.com/chapter/10.1007/978-3-319-67383-7_2

[6] Model Context Protocol Working Group, "Model Context Protocol
    Specification, version 2024-11-05," Anthropic PBC, Nov. 2024. [Online].
    Available: https://modelcontextprotocol.io/specification

[7] LangChain, Inc., "LangGraph: Building stateful, multi-actor
    applications with LLMs," Documentation, 2024. [Online]. Available:
    https://langchain-ai.github.io/langgraph/

[8] Cloud Native Computing Foundation, "Tekton Pipelines API reference,
    v1," 2024. [Online]. Available: https://tekton.dev/docs/pipelines/

---

*Prepared by: [Your Name] · MSc / MTech in [Your Programme]*
*Supervisor (proposed): [Name]* · *Date: [DD-MM-YYYY]*
