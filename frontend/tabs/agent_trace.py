"""Agent Trace tab — iteration-27.

Renders the machine-checkable observability record for any past pipeline
generation run. Two panels:

  1. **Recent runs** — dropdown fed by `GET /api/agents/traces/latest`.
  2. **Per-run timeline + details** — fed by `GET /api/agents/traces`.

Every panel is Markdown-driven so we avoid the Gradio 4.44.1 nested-Tabs
crash and keep the UI deterministic for automated screenshots in the
thesis appendix.
"""

from __future__ import annotations

from typing import Any

import gradio as gr

from frontend.components.api_client import get


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def _fetch_latest_runs() -> list[dict[str, Any]]:
    try:
        payload = get("/api/agents/traces/latest?limit=25") or {}
        return payload.get("runs") or []
    except Exception:
        return []


def _fetch_run(run_id: str) -> dict[str, Any]:
    try:
        return get(f"/api/agents/traces?run_id={run_id}") or {}
    except Exception:
        return {}


def _choice_label(run: dict[str, Any]) -> str:
    """Compact one-liner used in the dropdown."""
    when = (run.get("created_at") or "")[:19].replace("T", " ")
    ci = run.get("ci_platform", "?")
    cloud = run.get("cloud_platform", "?")
    dur = (run.get("total_duration_ms") or 0) / 1000.0
    n = run.get("trace_count") or 0
    failed = run.get("failed_agents") or 0
    tag = " ⚠" if failed else ""
    return f"{when} · {ci}/{cloud} · {n} agents · {dur:.1f}s{tag}"


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def _render_summary(payload: dict[str, Any]) -> str:
    if not payload or not payload.get("traces"):
        return "_No traces for this run — pick a different one or generate a new pipeline._"

    m = payload.get("run_meta") or {}
    t = payload.get("totals") or {}
    lines = [
        f"### Run summary",
        f"| | |",
        f"|---|---|",
        f"| Repository | `{m.get('repository_url') or '—'}` |",
        f"| CI · Cloud | `{m.get('ci_platform')}` · `{m.get('cloud_platform')}` |",
        f"| Custom directive | { (m.get('custom_requirement') or '—').replace('|','/')[:200] } |",
        f"| Status | `{m.get('status')}` · total {float(m.get('generation_seconds') or 0):.1f}s |",
        f"| Agents run | **{t.get('agent_count', 0)}** ({t.get('failed_count', 0)} failed) |",
        f"| LLM tokens | prompt **{t.get('prompt_tokens', 0):,}**, completion **{t.get('completion_tokens', 0):,}** |",
        f"| LLM cost | **${float(t.get('cost_usd') or 0):.4f}** |",
        f"| MCP tool calls | **{t.get('mcp_call_count', 0)}** |",
        "",
    ]
    return "\n".join(lines)


def _render_timeline(payload: dict[str, Any]) -> str:
    """ASCII-style timeline bar chart — cheap, works in Markdown."""
    traces = payload.get("traces") or []
    if not traces:
        return ""
    total_ms = max(1, sum(t["duration_ms"] for t in traces))
    max_bar = 40
    lines = ["### Timeline", "```"]
    for t in traces:
        dur = t["duration_ms"]
        pct = dur / total_ms
        bar = "█" * max(1, int(pct * max_bar))
        icon = "✓" if t["status"] == "ok" else "✗"
        lines.append(f"{icon} {t['agent_name']:<26} {bar:<40} {dur/1000:6.2f}s  ({pct*100:5.1f}%)")
    lines.append("```")
    return "\n".join(lines)


def _render_per_agent_cards(payload: dict[str, Any]) -> str:
    traces = payload.get("traces") or []
    if not traces:
        return ""
    out = ["### Per-agent detail"]
    for t in traces:
        status_icon = "✅" if t["status"] == "ok" else "❌"
        out.append(f"\n#### {status_icon} {t['step_index']+1}. {t['agent_name']} — {t['duration_ms']/1000:.2f}s")

        # Input & output shape
        inp = t.get("input_summary") or {}
        outp = t.get("output_summary") or {}
        out.append(
            f"- **Input keys**: `{', '.join(inp.get('keys_present') or []) or '—'}`\n"
            f"- **Output keys added**: `{', '.join(outp.get('keys_added') or []) or '—'}`"
        )
        if inp.get("custom_requirement"):
            out.append(f"- **Custom directive seen**: `{inp['custom_requirement'][:120]}`")

        # LLM detail
        if t.get("llm_provider"):
            out.append(
                f"- **LLM**: `{t['llm_provider']}/{t['llm_model']}` · "
                f"prompt {t['prompt_tokens']:,} · completion {t['completion_tokens']:,} · "
                f"**${float(t.get('cost_usd') or 0):.4f}**"
            )
        else:
            out.append("- **LLM**: _(none — deterministic agent)_")

        # Prompt collapsible
        if t.get("prompt_text"):
            prompt = t["prompt_text"].replace("`", "'")
            out.append(
                f"<details><summary>Prompt sent to LLM ({len(prompt):,} chars)</summary>\n\n"
                f"```\n{prompt[:6000]}\n```\n\n</details>"
            )

        # Skills declared
        skills = t.get("skills_declared") or []
        if skills:
            out.append(f"- **Skills declared (guard whitelist)**: {' · '.join(f'`{s}`' for s in skills)}")

        # MCP calls
        mcp = t.get("mcp_calls") or []
        if mcp:
            out.append(f"- **MCP tool calls** ({len(mcp)}):")
            for m in mcp:
                ok = "✓" if m.get("ok") else "✗"
                out.append(f"  - {ok} `{m.get('adapter')}.{m.get('tool')}` — {m.get('duration_ms')}ms · args=`{m.get('args_summary','')[:80]}`")
        else:
            out.append("- **MCP tool calls**: _none_")

        if t.get("error"):
            out.append(f"- **Error**: `{t['error'][:400]}`")

    return "\n".join(out)


def _render_full(payload: dict[str, Any]) -> str:
    if not payload:
        return "_Pick a run above to load its trace._"
    return (
        _render_summary(payload) + "\n"
        + _render_timeline(payload) + "\n\n"
        + _render_per_agent_cards(payload)
    )


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------
def _refresh_runs():
    runs = _fetch_latest_runs()
    choices = [(_choice_label(r), r["run_id"]) for r in runs]
    if not choices:
        return gr.update(choices=[], value=None), "_No runs yet — generate a pipeline first._"
    first_id = choices[0][1]
    payload = _fetch_run(first_id)
    return gr.update(choices=choices, value=first_id), _render_full(payload)


def _load_run(run_id: str):
    if not run_id:
        return "_Pick a run above._"
    return _render_full(_fetch_run(run_id))


# ---------------------------------------------------------------------------
# Tab builder
# ---------------------------------------------------------------------------
def build_tab(*, token_state=None):  # token_state accepted for API parity
    with gr.Column():
        gr.Markdown(
            "### Agent execution trace\n"
            "Every pipeline generation opens seven agent nodes. Each row "
            "below shows what the agent **saw** (input state), what it "
            "**sent** to the LLM (prompt), which **skills** the guard "
            "allowed, which **MCP tools** it actually invoked, and how "
            "much **cost** and **time** it took — end-to-end evidence "
            "for the thesis Evaluation chapter."
        )

        with gr.Row():
            run_selector = gr.Dropdown(
                label="Recent runs (newest first)",
                choices=[], value=None, interactive=True,
                elem_id="agent-trace-run-select",
            )
            refresh_btn = gr.Button("Refresh", elem_id="agent-trace-refresh")

        trace_md = gr.Markdown(
            value="_Click Refresh to load the most recent runs._",
            elem_id="agent-trace-md",
        )

        refresh_btn.click(
            _refresh_runs, inputs=None, outputs=[run_selector, trace_md],
        )
        run_selector.change(
            _load_run, inputs=[run_selector], outputs=[trace_md],
        )
