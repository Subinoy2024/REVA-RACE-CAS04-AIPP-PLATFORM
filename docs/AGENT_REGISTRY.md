# AIPP · Agent Registry & Skill Contracts

> **Audience:** thesis committee, other AIPP maintainers, and any external
> AI system that wants to discover what AIPP can do.
> **TL;DR:** every agent self-declares its skills. `GET /api/agents` returns
> the full catalog. No hardcoded assumptions anywhere else.

---

## 1 · Why we built a registry

Before Iteration-21, agents were **hard-wired** in
`backend/orchestrator/graph.py`. The only way to answer *"what agents exist
and what can each of them do?"* was to open source code.

That's a problem for three reasons:

1. **Reviewers can't audit** — a thesis committee shouldn't have to grep
   source to see the agent catalog.
2. **Frontends can't render dynamically** — the UI had to hardcode the
   7-agent list. Add an agent → break the UI.
3. **AI-to-AI discovery is impossible** — an external orchestrator (or
   another LLM) can't ask AIPP *"what can you do?"* without a formal
   contract.

The **agent registry** solves all three by making agents **self-describing**.

---

## 2 · Where does the registry live?

| File | Purpose |
|------|---------|
| `backend/agents/skills.py` | The `AgentSkill` dataclass — the contract |
| `backend/agents/registry.py` | The registry itself + population logic |
| `server.py :: GET /api/agents` | Public read-only endpoint |
| `backend/tests/test_iteration_21_...` | Regression tests |

---

## 3 · How does an `AgentSkill` look?

```python
AgentSkill(
    name="repository_analysis",              # stable ID (LangGraph node name)
    label="Repository Analysis Agent",       # UI title
    description="Reads the target repo …",   # one-sentence summary
    skills=[                                 # capabilities (bullet-list)
        "clone_repo_tree_read_only",
        "detect_dependency_files",
        "detect_dockerfiles_and_manifests",
        "detect_existing_ci_pipelines",
        "extract_readme_summary",
    ],
    inputs=RepositoryRequest,                # Pydantic model
    outputs=RepositoryAnalysis,              # Pydantic model
    reads_mcp=["github"],                    # MCP adapters used read-only
    writes_mcp=[],                           # MCP adapters used for writes
    depends_on=[],                           # upstream agent names
    llm_backed=False,                        # does it spend LLM tokens?
)
```

Every field is deliberately small and JSON-safe. `to_card()` returns the
same information as a plain dict — that's the **AIPP equivalent of an A2A
"agent card"**.

---

## 4 · Why not the A2A protocol?

Google's **A2A (Agent-to-Agent) protocol** (2024) proposes an HTTP-based
JSON-RPC transport for agents to discover each other and delegate work.
It's fantastic for cross-organisation orchestration.

AIPP does **not** use A2A because:

| Property | A2A assumes | AIPP reality |
|----------|-------------|--------------|
| Agent location | Different processes / different orgs | One FastAPI process |
| Transport | HTTP + JSON-RPC | In-process Python calls |
| Typing | Dynamic JSON schema | Compile-time Pydantic models |
| Discovery | Agent cards on `/.well-known/` | `GET /api/agents` |
| Latency budget | Tens of ms per hop | Microseconds (same process) |

Adding A2A to a single-process app would introduce a **network hop for
zero benefit**. The correct pattern for in-process multi-agent is what
we chose: **LangGraph** shared state + typed Pydantic I/O.

We keep the *idea* of A2A (self-describing agents) via `AgentSkill`; we
skip the *transport* (HTTP) because we don't need it.

> **In the thesis:** cite A2A as the "cross-org" pattern and explain why
> AIPP's in-process nature makes LangGraph the correct primitive.

---

## 5 · How to add a new agent (recipe)

1. Write the agent class in `backend/agents/<name>_agent.py`.
   Small: system prompt + `_build_prompt(state)` + `response_model`.
2. Add a Pydantic model for its `outputs` in `backend/models/`.
3. Register it in `backend/agents/registry.py`:
   ```python
   register_agent(AgentSkill(
       name="my_new_agent",
       label="My New Agent",
       description="One line, action-oriented.",
       skills=["do_a_thing", "do_another_thing"],
       outputs=MyOutputSchema,
       depends_on=["technology_detection"],
   ))
   ```
4. Add the node to `orchestrator/graph.py`:
   `sg.add_node("my_new_agent", _track("my_new_agent", node_my_new))`
5. Add a test case in `test_iteration_21_agent_registry_and_security.py`
   to confirm the new agent shows up in `list_agents()`.

That's it — the UI's *About the agents* panel and the `/api/agents`
endpoint automatically show the new agent with no extra wiring.

---

## 6 · Contract for consumers

`GET /api/agents` returns:

```json
{
  "total": 8,
  "agents": [
    {
      "name": "repository_analysis",
      "label": "Repository Analysis Agent",
      "description": "...",
      "skills": ["...", "..."],
      "inputs": "RepositoryRequest",
      "outputs": "RepositoryAnalysis",
      "reads_mcp": ["github"],
      "writes_mcp": [],
      "depends_on": [],
      "llm_backed": false
    },
    ...
  ]
}
```

**Stability guarantee:** field names never change. New fields may be
added; existing fields will not disappear. Treat this endpoint as public.

---

## 7 · Skills as a **security boundary**

Because every agent's `reads_mcp` / `writes_mcp` list is declared up-front,
future work can enforce:

- The MCP client refuses a `call()` from an agent whose skill card doesn't
  list that adapter → **defence-in-depth against a prompt-injected agent**.
- Audit-log every deviation → alerting.

This is out of scope for the thesis but **already unlocked** by the design.
