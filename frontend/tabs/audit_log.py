"""Gradio tab — Audit Log viewer.

Reads the last N rows from the AuditLog table via
`GET /api/research/audit?limit=N` and renders them as a compact Markdown
table. Every agent decision (`pipeline.generate.start / done / error`,
`pipeline.rca.done`, `deployment.commit.*`) writes a row to that table,
so this tab is the go-to place for troubleshooting a failed run or
verifying that a PAT-authenticated write actually happened.

No PAT / secret content is ever stored in `details_json` — see
`backend/services/audit_service.py`.
"""

from __future__ import annotations

import json
from typing import Any

import gradio as gr

from frontend.components.api_client import get


# Actions that indicate an error / warning — we colourise the marker for
# quicker scanning. Everything else is treated as a normal event.
_WARN_ACTIONS = ("error", "failed", "warning", "reject")


def _marker(action: str) -> str:
    a = (action or "").lower()
    if any(w in a for w in _WARN_ACTIONS):
        return "🔴"
    if "done" in a or "complete" in a or "ok" in a:
        return "🟢"
    if "start" in a or "begin" in a:
        return "🔵"
    return "⚪️"


def _short_details(details: Any, max_len: int = 220) -> str:
    """One-line, escaped preview of the `details_json` blob."""
    if details is None:
        return "-"
    try:
        text = json.dumps(details, sort_keys=True, default=str)
    except Exception:                                       # noqa: BLE001
        text = str(details)
    text = text.replace("|", "\\|").replace("\n", " ")
    return (text[: max_len - 1] + "…") if len(text) > max_len else text


def _refresh(limit: int) -> tuple[str, str]:
    try:
        rows = get("/api/research/audit", params={"limit": int(limit)})
    except Exception as e:                                  # noqa: BLE001
        return f"❌ Failed to reach backend: {e}", ""

    if not rows:
        return (
            "ℹ️ No audit entries yet — generate a pipeline or run "
            "PipelineDoctor and refresh.",
            "",
        )

    md = ["| # | When (UTC) | Action | Actor / Tool | Details |",
          "|---|------------|--------|--------------|---------|"]
    for i, r in enumerate(rows, start=1):
        actor = r.get("actor") or "-"
        tool = r.get("tool") or "-"
        who = actor if actor == "-" else f"{actor} / {tool}"
        md.append(
            f"| {i} "
            f"| {r.get('created_at', '-')} "
            f"| {_marker(r.get('action', ''))} `{r.get('action', '-')}` "
            f"| {who} "
            f"| {_short_details(r.get('details'))} |"
        )
    header = f"✅ Loaded **{len(rows)}** most recent audit entries"
    return header, "\n".join(md)


def _download_full() -> gr.File:
    """Dump the raw JSON payload so the user can grep it locally."""
    try:
        rows = get("/api/research/audit", params={"limit": 500})
    except Exception:                                       # noqa: BLE001
        rows = []
    import os
    import tempfile
    tmp = tempfile.mkdtemp(prefix="aipp_audit_")
    path = os.path.join(tmp, "audit_log.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, default=str)
    return gr.update(value=path, visible=True)


def _download_csv() -> gr.File:
    """Export audit log as CSV for ISO 27001 compliance reporting."""
    try:
        rows = get("/api/research/audit", params={"limit": 500})
    except Exception:                                       # noqa: BLE001
        rows = []
    import csv
    import os
    import tempfile
    tmp = tempfile.mkdtemp(prefix="aipp_audit_csv_")
    path = os.path.join(tmp, "audit_log_iso27001.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Index", "Timestamp_UTC", "Action", "Actor", "Tool", "Details"])
        for i, r in enumerate(rows, start=1):
            writer.writerow([
                i, r.get("created_at", ""), r.get("action", ""),
                r.get("actor", ""), r.get("tool", ""),
                json.dumps(r.get("details", {}), default=str)
            ])
    return gr.update(value=path, visible=True)


def build_tab() -> None:
    with gr.Column():
        gr.Markdown(
            "### Audit Log & Compliance Export\n"
            "Every agent decision, security gate check, and workflow action writes an append-only row "
            "to PostgreSQL `audit_logs`. Export raw JSON or ISO 27001 CSV compliance reports below."
        )
        with gr.Row():
            limit = gr.Slider(
                minimum=10, maximum=500, step=10, value=50,
                label="How many entries to view",
                elem_id="audit-limit",
            )
            refresh_btn = gr.Button("↻ Refresh", variant="primary", elem_id="audit-refresh")
            download_btn = gr.Button("⬇ Download JSON", elem_id="audit-download")
            download_csv_btn = gr.Button("📊 Export ISO 27001 CSV", elem_id="audit-download-csv")

        status = gr.Markdown(elem_id="audit-status")
        table = gr.Markdown(elem_id="audit-table")
        download = gr.File(label="audit_log.json", visible=False, elem_id="audit-download-file")
        download_csv = gr.File(label="audit_log_iso27001.csv", visible=False, elem_id="audit-download-csv-file")

        refresh_btn.click(_refresh, inputs=[limit], outputs=[status, table])
        download_btn.click(_download_full, inputs=[], outputs=[download])
        download_csv_btn.click(_download_csv, inputs=[], outputs=[download_csv])
