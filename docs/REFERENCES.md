# AIPP — Academic References

Cross-references used by the AIPP thesis (Chapter 2 · Literature Review) and
by the source-code comments across `/app/backend/` and `/app/frontend/`.

Every entry lists:
- the exact author list + title as it appears in the source,
- the venue and year,
- an **open-access URL** where the full PDF can be downloaded (arXiv,
  publisher's HTML, or the author's institutional page),
- the DOI where one exists,
- how AIPP applies the idea.

If your university thesis system requires a `.bib` file, use
[`REFERENCES.bib`](./REFERENCES.bib) alongside this file.

---

## [1] RepoCoder — repository-level context for LLM code generation

- **Authors:** Fengji Zhang, Bei Chen, Yue Zhang, Jacky Keung, Jin Liu,
  Daoguang Zan, Yi Mao, Jian-Guang Lou, Weizhu Chen
- **Title:** *RepoCoder: Repository-Level Code Completion Through Iterative
  Retrieval and Generation*
- **Venue:** EMNLP 2023 (Empirical Methods in NLP)
- **Open-access PDF:** <https://arxiv.org/pdf/2303.12570>
- **arXiv page:** <https://arxiv.org/abs/2303.12570>
- **DOI:** [10.18653/v1/2023.emnlp-main.151](https://doi.org/10.18653/v1/2023.emnlp-main.151)
- **Applied in AIPP:** the **Repository Analysis agent**
  (`backend/agents/repository_analysis.py`) collects the file tree, dependency
  manifests, Dockerfiles, and Kubernetes/Helm files *before* any LLM
  generation call. This mirrors RepoCoder's retrieval-before-generation loop,
  applied at pipeline scope instead of code-completion scope.

## [2] AutoGen — multi-agent orchestration for LLMs

- **Authors:** Qingyun Wu, Gagan Bansal, Jieyu Zhang, Yiran Wu, Beibin Li,
  Erkang Zhu, Li Jiang, Xiaoyun Zhang, Shaokun Zhang, Jiale Liu, Ahmed Awadallah,
  Ryen W. White, Doug Burger, Chi Wang
- **Title:** *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent
  Conversation*
- **Venue:** arXiv 2023 (Microsoft Research)
- **Open-access PDF:** <https://arxiv.org/pdf/2308.08155>
- **arXiv page:** <https://arxiv.org/abs/2308.08155>
- **Microsoft Research landing page:**
  <https://www.microsoft.com/en-us/research/publication/autogen-enabling-next-gen-llm-applications-via-multi-agent-conversation-framework/>
- **Applied in AIPP:** the **7-agent LangGraph state machine**
  (`backend/orchestrator/graph.py`). Each agent has a single well-defined
  responsibility (repo analysis, tech detection, architecture, planner, YAML
  generator, environment validator, RCA). LangGraph — not AutoGen directly —
  provides the graph substrate, but the *design* pattern (many small agents
  over one giant prompt) is AutoGen's contribution.

## [3] Empirical analysis of Travis CI failures

- **Authors:** Moritz Beller, Georgios Gousios, Andy Zaidman *(most-cited
  Travis-CI failure study; the 3.7M-build analysis your Chapter 2 cites is
  Gallaba et al. 2018 — both are listed below since the surface claim uses
  both datasets.)*

### 3a — Beller / Gousios / Zaidman · original Travis empirical study
- **Title:** *Oops, My Tests Broke the Build: An Explorative Analysis of
  Travis CI with GitHub*
- **Venue:** MSR 2017 (Mining Software Repositories)
- **Open-access PDF:**
  <https://research.tudelft.nl/files/28105598/msr17_authorversion.pdf>
- **DOI:** [10.1109/MSR.2017.62](https://doi.org/10.1109/MSR.2017.62)

### 3b — Gallaba et al. · 3.7 million-build noise/heterogeneity study
- **Authors:** Keheliya Gallaba, Christian Macho, Martin Pinzger, Shane
  McIntosh
- **Title:** *Noise and Heterogeneity in Historical Build Data: An Empirical
  Study of Travis CI*
- **Venue:** ASE 2018 (Automated Software Engineering)
- **Open-access PDF:** <https://mitschi.github.io/preprints/ase2018gallaba.pdf>
- **DOI:** [10.1145/3238147.3238171](https://doi.org/10.1145/3238147.3238171)

- **Applied in AIPP:** the **PipelineDoctor RCA agent**
  (`backend/agents/rca_agent.py`) categorises log lines into the standard
  failure classes derived from these studies (dependency errors, flaky
  tests, image-pull failures, missing env vars) and requires the LLM to
  quote a **verbatim log line** for every suggested cause — no invention.

## [4] Toolformer — tool-augmented LLMs reduce hallucination

- **Authors:** Timo Schick, Jane Dwivedi-Yu, Roberto Dessì, Roberta Raileanu,
  Maria Lomeli, Luke Zettlemoyer, Nicola Cancedda, Thomas Scialom
- **Title:** *Toolformer: Language Models Can Teach Themselves to Use Tools*
- **Venue:** arXiv 2023 (Meta AI)
- **Open-access PDF:** <https://arxiv.org/pdf/2302.04761>
- **arXiv page:** <https://arxiv.org/abs/2302.04761>
- **Applied in AIPP:** the **MCP integration layer**
  (`backend/mcp/`). Agents cannot answer from prior knowledge — they must
  invoke a real adapter (GitHub, Azure DevOps, AWS, GCP, n8n, Kubernetes,
  Harness, Tekton, GitLab, Azure) and use the *returned* data. When an
  adapter is unconfigured, it returns a well-formed `ToolNotConfigured`
  error rather than fabricating a response. This is Toolformer's design
  principle applied at MCP-adapter granularity.

## [5] DevSecOps — Myrbakken & Colomo-Palacios

- **Authors:** Håvard Myrbakken, Ricardo Colomo-Palacios
- **Title:** *DevSecOps: A Multivocal Literature Review*
- **Venue:** SPICE 2017 (Software Process Improvement and Capability
  dEtermination)
- **Open-access PDF:** <https://www.rcolomo.com/papers/314.pdf>
- **Publisher DOI:** [10.1007/978-3-319-67383-7_2](https://doi.org/10.1007/978-3-319-67383-7_2)
- **Applied in AIPP:** three DevSecOps principles the paper singles out as
  recurring across the literature — **automation, continuous monitoring,
  and immutable audit trails** — map directly to AIPP's design:
  - *Automation* → the multi-agent generator + 5-CI-parity output.
  - *Continuous monitoring* → the LLM-usage meter, the Audit Log tab, and
    the SSE progress bus.
  - *Immutable audit trails* → every agent decision, every MCP write, and
    every deployment commit is persisted to the `audit_logs` Postgres
    table (`backend/services/audit_service.py`).
  - *Production approval gate* → the environment validator refuses any
    generated plan in which Production does not require manual approval.

## [6] LangGraph — stateful multi-agent orchestration for LLMs

- **Authors:** Harrison Chase et al. (LangChain, Inc.)
- **Title:** *LangGraph: Stateful, Multi-Actor Applications with LLMs*
- **Venue:** Official documentation + open-source implementation, 2024
- **Documentation:** <https://langchain-ai.github.io/langgraph/>
- **Introduction blog:** <https://www.langchain.com/blog/langgraph>
- **Source repository:** <https://github.com/langchain-ai/langgraph>
- **Applied in AIPP:** the **entire orchestration substrate**
  (`backend/orchestrator/graph.py`, `orchestrator/workflows.py`,
  `orchestrator/state.py`, `orchestrator/progress.py`). AIPP models its
  7-agent pipeline as a LangGraph `StateGraph` with explicit nodes and edges,
  which gives us: (a) durable per-agent status streamed to the UI via SSE,
  (b) resumable execution (a failing agent can be retried without redoing
  earlier agents), and (c) branching for the RCA path in PipelineDoctor.

## [7] Model Context Protocol (MCP) — Anthropic

- **Authors:** Anthropic, PBC (announced by Mike Krieger)
- **Title:** *Introducing the Model Context Protocol*
- **Venue:** Anthropic announcement + open specification, November 2024
- **Announcement:** <https://www.anthropic.com/news/model-context-protocol>
- **Specification:** <https://spec.modelcontextprotocol.io/>
- **SDK / servers repository:** <https://github.com/modelcontextprotocol>
- **Applied in AIPP:** the **eleven MCP adapters**
  (`backend/mcp/adapters/*.py`). AIPP treats every external system —
  GitHub, Azure DevOps, GitLab, Harness, Tekton, Kubernetes, Azure, AWS,
  GCP, n8n — as an MCP-style tool surface. Agents cannot embed vendor
  SDKs directly; they must call `mcp.call("<adapter>", "<tool>", **args)`.
  This gives the audit log a uniform record shape, makes new integrations
  drop-in, and keeps the LLM's tool surface identical across providers.

## [8] GitOps — Operations by Pull Request

- **Author:** Alexis Richardson (Weaveworks CEO)
- **Title:** *GitOps: Operations by Pull Request*
- **Venue:** Weaveworks blog post, August 2017 (the founding text)
- **Original article:** <https://medium.com/weaveworks/gitops-operations-by-pull-request-14e8b659b058>
- **Follow-up "What is GitOps, really?":**
  <https://medium.com/weaveworks/what-is-gitops-really-e77329f23416>
- **Weaveworks keynote deck (AWS re:Invent):**
  <https://d1.awsstatic.com/product-marketing/EKS/3.%20Alexis%20Richardson%20-%20Weaveworks%20Keynote.pdf>
- **Applied in AIPP:** the **"Commit YAML to repo" flow**
  (`frontend/tabs/pipeline_generator.py` + `backend/api/deployment.py`).
  AIPP never runs `terraform apply` or `kubectl apply` on your behalf — it
  writes the generated pipeline file back to a branch you explicitly picked
  and lets your CI/CD platform reconcile from there. Every generated
  Terraform infra flow uses a manual-approval gate before apply, matching
  Richardson's "pull-request-based operations" principle: the Git history
  is the source of truth, and every change is peer-reviewed.

---

## How to fetch the PDFs

All five URLs point at publicly downloadable copies (arXiv preprints or
authors' institutional PDFs). If a link ever 404s, the corresponding DOI
resolves to the publisher's page — every one of these papers is either
open-access or the pre-print is authorised by the venue's copyright policy.

```bash
# One-liner to download all 5 preprints into ./docs/pdfs/
mkdir -p docs/pdfs && cd docs/pdfs \
  && curl -LO https://arxiv.org/pdf/2303.12570 \
  && curl -LO https://arxiv.org/pdf/2308.08155 \
  && curl -LO https://mitschi.github.io/preprints/ase2018gallaba.pdf \
  && curl -LO https://arxiv.org/pdf/2302.04761 \
  && curl -LO https://www.rcolomo.com/papers/314.pdf
```

If you're working from within a corporate/VPN network that blocks arXiv,
the same PDFs are also mirrored on the authors' institutional pages —
e.g. Microsoft Research (AutoGen), Meta AI (Toolformer), Ostfold University
College (Myrbakken/Colomo-Palacios).
