"""Agents Panel — read-only card grid rendered from `GET /api/agents`.

Purpose:
  - Thesis reviewers see the agent skill matrix without opening code.
  - Consumers (other AI systems) can also cURL the same endpoint.

Notes:
  - We fetch the catalog once at tab-build time (registry doesn't change
    at runtime). A refresh button re-fetches for good measure.
"""

from __future__ import annotations

import gradio as gr

from frontend.components.api_client import get


def _fetch_agents() -> list[dict]:
    try:
        payload = get("/api/agents") or {}
        return payload.get("agents", []) or []
    except Exception:
        return []


def _card_md(agent: dict) -> str:
    skills = agent.get("skills") or []
    reads = agent.get("reads_mcp") or []
    writes = agent.get("writes_mcp") or []
    dep = agent.get("depends_on") or []
    llm = "🧠 LLM-backed" if agent.get("llm_backed") else "⚙ Deterministic"
    inp = agent.get("inputs") or "—"
    out = agent.get("outputs") or "—"

    skills_md = "\n".join(f"- `{s}`" for s in skills)
    reads_md = ", ".join(f"`{a}`" for a in reads) or "_none_"
    writes_md = ", ".join(f"`{a}`" for a in writes) or "_none_"
    dep_md = ", ".join(f"`{a}`" for a in dep) or "_none_"

    return (
        f"### {agent.get('label', agent.get('name'))}\n"
        f"`{agent.get('name')}` · {llm}\n\n"
        f"{agent.get('description', '')}\n\n"
        f"**Skills**\n{skills_md}\n\n"
        f"**I/O** · inputs → `{inp}` · outputs → `{out}`\n\n"
        f"**MCP** · reads: {reads_md} · writes: {writes_md}\n\n"
        f"**Depends on**: {dep_md}"
    )


def _render(agents: list[dict]) -> str:
    if not agents:
        return "⚠ Could not fetch the agent catalog. Is the backend running?"
    header = (
        f"### {len(agents)} agents registered\n"
        "This catalog is served by `GET /api/agents`. Every agent "
        "self-declares its skills, inputs, outputs, and the MCP adapters "
        "it is authorised to call. Unlisted adapter calls are blocked at "
        "runtime by the [MCP Guard](/docs/AGENT_REGISTRY.md).\n\n---\n"
    )
    return header + "\n\n---\n\n".join(_card_md(a) for a in agents)


def build_tab() -> None:
    with gr.Column():
        gr.Markdown(
            "## Agent Catalog\n"
            "Self-describing agents — the AIPP equivalent of the A2A "
            "protocol's *agent card*, exposed at `/api/agents`."
        )
        # Iteration-25 fix: DO NOT fetch at build time. A synchronous HTTP
        # call here blocks the Svelte event loop during Tabs hydration and
        # triggers the Gradio 4.44 `addEventListener` cascade that kills
        # button clicks globally. The Refresh button + `demo.load` warm-up
        # populate the panel after mount.
        panel = gr.Markdown(
            value="_Click **↻ Refresh** to load the agent catalog._",
            elem_id="agents-panel",
        )
        refresh_btn = gr.Button("↻ Refresh", elem_id="agents-refresh")
        refresh_btn.click(
            lambda: _render(_fetch_agents()),
            inputs=None, outputs=[panel],
        )
