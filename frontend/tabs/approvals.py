"""Gradio tab — HITL Approvals audit trail.

Renders every Slack Block Kit button click that was routed through
`/api/slack/interactions`. Each row captures the exact question that
would appear on an ISO 27001 change-management ticket:

  * WHEN did the decision happen?
  * WHO clicked (Slack username + user ID)?
  * WHAT was decided (approve / reject)?
  * WHICH workflow / execution?
  * WHERE was it posted (Slack channel)?

Backed by `GET /api/slack/approvals` which reads the audit_logs table
filtered by `action='slack.hitl.decision'`. No secrets or resume tokens
are ever surfaced — see backend/api/slack.py for the audit payload.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime

import gradio as gr

from frontend.components.api_client import get


def _fmt_ts(iso: str) -> str:
    """Turn `2026-02-18T11:22:33.456789+00:00` into `2026-02-18 11:22 UTC`."""
    if not iso:
        return "-"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:                                       # noqa: BLE001
        return iso


def _marker(decision: str) -> str:
    return {"approve": "🟢", "reject": "🔴"}.get(
        (decision or "").lower(), "⚪️"
    )


def _cell(val, dash_when_empty: bool = True) -> str:
    """Markdown-safe cell rendering — escape pipes, collapse newlines."""
    if val in (None, "", "?"):
        return "-" if dash_when_empty else ""
    return str(val).replace("|", "\\|").replace("\n", " ")


def _summarise(rows: list[dict]) -> str:
    """Top-of-tab counter — one line, four numbers."""
    total = len(rows)
    approves = sum(1 for r in rows if (r.get("decision") or "").lower() == "approve")
    rejects = sum(1 for r in rows if (r.get("decision") or "").lower() == "reject")
    unique_users = len({r.get("user") for r in rows if r.get("user")})
    return (
        f"**{total}** decisions · "
        f"🟢 {approves} approved · "
        f"🔴 {rejects} rejected · "
        f"👥 {unique_users} unique approver(s)"
    )


def _refresh(limit: int, decision_filter: str, user_filter: str
             ) -> tuple[str, str, str]:
    """Fetch approvals from the API and render a markdown table."""
    try:
        data = get("/api/slack/approvals", params={"limit": int(limit)})
    except Exception as e:                                  # noqa: BLE001
        return (
            f"❌ Failed to reach AIPP backend: {e}",
            "",
            "_no data_",
        )

    rows = (data or {}).get("approvals", []) or []
    # Client-side filters — cheap on 100 rows, keeps the API generic.
    if decision_filter and decision_filter.lower() != "all":
        want = decision_filter.lower()
        rows = [r for r in rows if (r.get("decision") or "").lower() == want]
    if user_filter.strip():
        needle = user_filter.strip().lower()
        rows = [r for r in rows
                if needle in (r.get("user") or "").lower()
                or needle in (r.get("user_id") or "").lower()]

    if not rows:
        return (
            "ℹ️ No HITL decisions match the current filters yet. "
            "Click **Approve** or **Reject** on a Slack HITL card and "
            "refresh this tab.",
            _summarise(rows),
            "_no data_",
        )

    md = [
        "| # | When | Decision | Who | Channel | Workflow | n8n Exec | HTTP |",
        "|---|------|----------|-----|---------|----------|----------|------|",
    ]
    for i, r in enumerate(rows, start=1):
        exec_id = r.get("n8n_execution_id")
        n8n_status_code = r.get("n8n_status")
        md.append(
            f"| {i} "
            f"| {_fmt_ts(r.get('when', ''))} "
            f"| {_marker(r.get('decision', ''))} "
            f"`{_cell(r.get('decision'))}` "
            f"| `{_cell(r.get('user'))}` "
            f"({_cell(r.get('user_id'), dash_when_empty=False)}) "
            f"| `#{_cell(r.get('channel'))}` "
            f"| {_cell(r.get('workflow_hint'))} "
            f"| `{_cell(exec_id)}` "
            f"| `{_cell(n8n_status_code)}` |"
        )

    status = f"✅ Loaded **{len(rows)}** HITL decision(s)"
    summary = _summarise(rows)
    return status, summary, "\n".join(md)


def _download_json(limit: int) -> gr.File:
    """Full-fidelity JSON dump for compliance attachments / thesis appendices."""
    try:
        data = get("/api/slack/approvals", params={"limit": int(limit)})
    except Exception:                                       # noqa: BLE001
        data = {"approvals": [], "total": 0}
    tmp = tempfile.mkdtemp(prefix="aipp_approvals_")
    path = os.path.join(tmp, "hitl_approvals.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    return gr.update(value=path, visible=True)


def build_tab() -> None:
    with gr.Column():
        gr.Markdown(
            "### HITL Approvals Audit Report\n"
            "Live compliance audit dashboard for Slack Human-In-The-Loop approvals. "
            "Approvals and rejections are executed in **Slack**; this tab tracks and reports "
            "all ISO 27001 change-management audit evidence."
        )
        
        summary = gr.Markdown(elem_id="approvals-summary")
        status = gr.Markdown(elem_id="approvals-status")
        
        with gr.Row():
            limit = gr.Slider(
                minimum=10, maximum=500, step=10, value=100,
                label="Decisions to load",
                elem_id="approvals-limit",
            )
            decision_filter = gr.Dropdown(
                choices=["All", "Approve", "Reject"],
                value="All",
                label="Filter by Decision",
                elem_id="approvals-decision-filter",
                interactive=True,
            )
            user_filter = gr.Textbox(
                value="",
                label="Filter by Approver Username (optional)",
                placeholder="e.g. subinoy.admin",
                elem_id="approvals-user-filter",
            )
        with gr.Row():
            refresh_btn = gr.Button("↻ Refresh Report", variant="primary",
                                    elem_id="approvals-refresh")
            download_btn = gr.Button("⬇ Download Audit Report (JSON)",
                                     elem_id="approvals-download")
            auto = gr.Checkbox(
                label="Auto-refresh every 20 s",
                value=False,
                elem_id="approvals-auto-refresh",
                info="Live-poll during demo runs so new Slack clicks appear automatically.",
            )

        table = gr.Markdown(elem_id="approvals-table")
        download = gr.File(label="hitl_approvals.json", visible=False,
                           elem_id="approvals-download-file")

        # Manual & filter change refresh handlers
        refresh_btn.click(
            _refresh,
            inputs=[limit, decision_filter, user_filter],
            outputs=[status, summary, table],
        )
        decision_filter.change(
            _refresh,
            inputs=[limit, decision_filter, user_filter],
            outputs=[status, summary, table],
        )
        user_filter.change(
            _refresh,
            inputs=[limit, decision_filter, user_filter],
            outputs=[status, summary, table],
        )
        download_btn.click(_download_json, inputs=[limit], outputs=[download])

        def _tick(is_on, lim, dec, usr):
            if not is_on:
                return gr.update(), gr.update(), gr.update()
            return _refresh(lim, dec, usr)

        timer = gr.Timer(20.0)
        timer.tick(
            _tick,
            inputs=[auto, limit, decision_filter, user_filter],
            outputs=[status, summary, table],
        )
