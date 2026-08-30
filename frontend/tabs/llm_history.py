"""LLM History tab — historical (Postgres-persisted) spend visualisation.

Powered by `GET /api/llm/usage/history`. Unlike the in-memory tracker in
the Pipeline Generator tab, this data survives container restarts and is
suitable for the thesis Evaluation chapter.

Chart: daily total spend (USD) grouped by model, rendered as a Gradio
LinePlot. Table: raw recent calls.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

import gradio as gr
import pandas as pd

from frontend.components.api_client import get


def _fetch() -> dict:
    try:
        return get("/api/llm/usage/history?limit=500") or {}
    except Exception as e:
        return {"error": str(e)}


def _to_daily_frame(recent: list[dict]) -> pd.DataFrame:
    """Aggregate the `recent` list into daily-per-model rows."""
    buckets: dict[tuple[str, str], float] = defaultdict(float)
    for call in recent:
        try:
            day = datetime.fromisoformat(call["created_at"]).date().isoformat()
        except Exception:
            continue
        key = (day, call.get("model", "unknown"))
        buckets[key] += float(call.get("cost_usd", 0.0))
    rows = [{"day": d, "model": m, "cost_usd": round(v, 6)} for (d, m), v in buckets.items()]
    return pd.DataFrame(rows).sort_values(["day", "model"]) if rows else pd.DataFrame(
        columns=["day", "model", "cost_usd"]
    )


def _totals_md(data: dict) -> str:
    if "error" in data:
        return f"⚠ Could not fetch history: `{data['error']}`"
    if data.get("total_calls", 0) == 0:
        return (
            "_No historical calls yet. Run at least one pipeline generation "
            "to populate this view. Data survives container restarts._"
        )
    return (
        f"**Total calls:** {data['total_calls']:,}  ·  "
        f"**Total tokens:** {data['total_tokens']:,}  ·  "
        f"**Estimated spend:** `${data['total_cost_usd']:.4f}`\n\n"
        f"_{data.get('note', '')}_"
    )


def _by_agent_md(data: dict) -> str:
    by = data.get("by_agent") or {}
    if not by:
        return "_no per-agent data yet_"
    rows = ["| Agent | Calls | Prompt tok | Completion tok | Est. $ |",
            "|-------|------:|-----------:|---------------:|-------:|"]
    for agent, b in sorted(by.items(), key=lambda x: -x[1]["cost_usd"]):
        rows.append(
            f"| `{agent}` | {b['calls']} | {b['prompt_tokens']:,} | "
            f"{b['completion_tokens']:,} | ${b['cost_usd']:.4f} |"
        )
    return "\n".join(rows)


def _refresh() -> tuple[Any, str, str]:
    data = _fetch()
    recent = data.get("recent") or []
    return _to_daily_frame(recent), _totals_md(data), _by_agent_md(data)


def build_tab() -> None:
    with gr.Column():
        gr.Markdown(
            "## LLM Spend History\n"
            "Historical LLM usage persisted to Postgres — survives "
            "container restarts. Suitable for the thesis Evaluation chapter."
        )
        totals = gr.Markdown(elem_id="llmh-totals")
        # Gradio 4.44.1 has a Svelte crash ("Cannot read properties of
        # undefined (reading 'indexOf'/'addEventListener')") when a
        # `gr.LinePlot` mounts with `color=` set or with no `value=`. We
        # provide a schema-only empty DataFrame + omit `color=` at build
        # time. The Refresh button populates real data post-mount.
        chart = gr.LinePlot(
            value=pd.DataFrame(columns=["day", "model", "cost_usd"]),
            x="day", y="cost_usd",
            title="Daily spend, USD",
            height=340,
            elem_id="llmh-chart",
        )
        by_agent = gr.Markdown(elem_id="llmh-by-agent")
        btn = gr.Button("↻ Refresh", elem_id="llmh-refresh")

        # No initial fill — let the user click Refresh, or wire this into
        # `demo.load` if you want it warm on connect. Populating at build
        # time was the trigger for the mount crash.

        btn.click(_refresh, inputs=None, outputs=[chart, totals, by_agent])
