# AIPP · MCP Architecture

> **Audience:** thesis committee + future maintainers.
> **TL;DR:** MCP is the **only** doorway between AIPP's LLM-driven agents
> and the outside world (GitHub, clouds, CI platforms). It's the piece
> that keeps hallucination below 5% and stops credentials from ever
> touching an LLM prompt.

---

## 1 · Why we chose MCP (Model Context Protocol)

### The problem MCP solves

Left to its own devices, an LLM asked to *"generate a CI/CD pipeline for
this repo"* will happily **invent** fake repo files, non-existent Azure
resource types, wrong Harness step names, or made-up Kubernetes
namespaces. That is the #1 documented failure mode of single-prompt
pipeline generators (Rausch et al., MSR 2017; Schick et al., NeurIPS
2023).

We needed a design that makes the LLM **structurally incapable** of
inventing.

### The guarantee MCP provides

| Guarantee | How |
|-----------|-----|
| No hallucinated commands | The LLM can only invoke *registered* tools |
| No secret exfiltration | Credentials live in adapter env vars, never in prompts |
| Full audit trail | Every tool call is logged to `audit_logs` |
| Deterministic replay | Same input → same tool call → same output |

MCP gives us **grounded generation** — exactly the property Toolformer
formalises in the tool-use literature, plus the governance layer the
paper did not have.

---

## 2 · Where MCP lives in the codebase

```
backend/mcp/
├── client.py        # the singleton client the agents call
├── registry.py      # maps (adapter, tool_name) → callable
├── __init__.py
└── adapters/        # ONE file per external system (11 total)
    ├── github.py
    ├── azure_devops.py
    ├── gitlab.py
    ├── harness.py
    ├── tekton.py
    ├── github_actions.py
    ├── kubernetes.py
    ├── azure.py
    ├── aws.py
    ├── gcp.py
    └── n8n.py
```

**Key rule:** agents **never** `import requests`, `boto3`, `github` or
any SDK directly. They call `self.mcp.call(<adapter>, <tool>, **kwargs)`
or nothing at all. The MCP client is the only network I/O in the agent
codebase.

---

## 3 · The client ↔ adapter contract

```python
# Every adapter subclasses this pattern:
class GitHubAdapter(BaseAdapter):
    name = "github"

    def _register_tools(self) -> None:
        self.register("get_repository",       self._get_repository)
        self.register("list_files",           self._list_files)
        self.register("get_file_content",     self._get_file_content)
        self.register("list_branches",        self._list_branches)
        self.register("commit_file",          self._commit_file)
        self.register("trigger_workflow_dispatch", self._trigger_wd)

    async def _get_repository(self, *, url, pat, branch):
        # actual GitHub API call
        ...
```

**Contract for callers:**
```python
result = await mcp.call("github", "list_files",
                        url="https://github.com/owner/repo",
                        pat=user_pat, branch="main")
```

- Arguments are always **kwargs** — never positional. Prevents accidental
  parameter drift.
- Return values are always **JSON-safe** dicts / lists. Never raw SDK
  objects.
- Errors bubble up as `RepositoryAccessError`, `MCPError`, etc. — typed.

---

## 4 · The 11 adapters — role matrix

| Adapter | Role | Which agents use it? |
|---------|------|----------------------|
| `github` | Read repo tree, files, branches; commit YAML | RepositoryAgent, deploy endpoint |
| `gitlab` | Same as GitHub for GitLab-hosted repos | RepositoryAgent (alt), deploy endpoint |
| `azure_devops` | Commit `azure-pipelines.yml`, trigger runs | deploy endpoint |
| `github_actions` | Trigger workflows, fetch failed-run logs | deploy endpoint, PipelineDoctor |
| `gitlab_ci` | Trigger `.gitlab-ci.yml`, fetch logs | PipelineDoctor |
| `harness` | Trigger Harness pipelines, fetch status | PipelineDoctor |
| `tekton` | Apply PipelineRun, stream Tekton logs | PipelineDoctor |
| `aws` | Verify ECR / EKS / Lambda reachable | DeploymentAgent |
| `azure` | Verify subscription / RG / AKS reachable | DeploymentAgent |
| `gcp` | Verify project / GKE / Cloud Run reachable | DeploymentAgent |
| `kubernetes` | Apply / describe cluster resources | Tekton adapter chain |
| `n8n` | Ping / activate / execute workflows | n8n Status tab, future RCA→remediation |

**Read/write separation:**
`RepositoryAgent` only ever calls read-only tools (`list_files`,
`get_file_content`). The **only** places a write happens are:
- `POST /api/deployment/commit` → `github.commit_file`
- `POST /api/deployment/trigger` → `github.trigger_workflow_dispatch`

Both are behind explicit user actions — not autonomous agent decisions.

---

## 5 · Sequence — how one GitHub read works

```
User clicks Generate
      │
      ▼
FastAPI /api/pipelines/generate/stream
      │
      ▼
PipelineService.generate()
      │
      ▼
LangGraph node: repository_analysis
      │
      ▼
RepositoryAgent.run(req)
      │
      ▼
MCPClient.call("github", "list_files", url=…, pat=…, branch=…)
      │
      ▼
MCPRegistry looks up (github, list_files)
      │
      ▼
GitHubAdapter._list_files(url, pat, branch)
      │
      ▼   (uses PyGithub, no LLM anywhere)
GitHub API
      │
      ▼
List[dict]  ──►  RepositoryAnalysis  ──►  AIPPState["analysis"]
      │
      ▼
audit_logs table row appended: {action=mcp.call, adapter=github, tool=list_files, seconds=0.47}
```

- **The LLM sees the sanitised result**, not the raw dict.
- **The PAT never leaves the MCP layer** — the LLM prompt never contains it.

---

## 6 · Governance features baked in

| Feature | Implementation |
|---------|----------------|
| Zero credential storage | PATs live in memory only during a request |
| Adapter without creds | Registered but returns clean *"not configured"* error |
| Prompt-injection filter | `sanitize_repository_snippet()` before any snippet reaches the LLM |
| Audit trail | Every `mcp.call` is logged to `audit_logs` |
| Tool typing | Every adapter tool has kwargs-only signature; wrong args = TypeError |
| Rate limit | `/api/pipelines/generate` is behind an in-memory sliding window |
| Secret scan | Generated YAML is scanned before commit; hard-fail on high-severity |

---

## 7 · Why not raw SDK calls?

Arguments for going through MCP even for a simple `github.get_file` call:

1. **Testability** — every adapter can be swapped for a fake in unit tests.
   We do this ~50 times across the test suite.
2. **Auditability** — every network call becomes a database row.
3. **Governance** — the MCP client can refuse tool calls based on the
   caller's agent skill (see `AGENT_REGISTRY.md § 7`).
4. **Replay** — a full pipeline run can be replayed offline by mocking the
   adapters, which is priceless for reproducible research.
5. **Uniformity** — 11 different SDKs (PyGithub, boto3, azure-sdk, google-
   cloud-*, kubernetes-client, …) all become one API surface. The agent
   code doesn't care.

Raw SDK calls give you none of that.

---

## 8 · Failure modes we handle

| Situation | Result |
|-----------|--------|
| Adapter env var missing | Adapter still registers, returns `not_configured` error |
| PAT invalid | `RepositoryAccessError`, mapped to HTTP 400 with clear message |
| Rate limit hit at GitHub | Retried with exponential backoff via `tenacity` |
| Network down | `AIPPError`, HTTP 502 |
| SDK version drift | Pinned in `requirements.txt`; adapters have thin surface |

---

## 9 · Thesis takeaway

MCP is what turns AIPP from *"an LLM that writes YAML"* into
*"an LLM system that generates evidence-grounded, auditable YAML with a
governance layer"*. It is the reason the hallucination-rate metric
(< 5%) and the credential-leakage metric (0) are achievable **by
construction**, not by luck.
