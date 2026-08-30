"""Gradio tab 3 — n8n workflow status + write actions.

Reads workflow metadata from the user's real n8n API (no bundled n8n).
Also lets the user:
  * Test connectivity to n8n (green/red banner + latency).
  * Execute a workflow on-demand.
  * Activate / deactivate a workflow.

All write actions go through audited `POST /api/workflows/n8n/{id}/{action}`
endpoints — see the Audit Log tab to inspect them after the fact.
"""

from __future__ import annotations

from typing import Any

import gradio as gr

from frontend.components.api_client import get, post


def _refresh() -> tuple[str, str, gr.update]:
    """Fetch workflows and return (header, markdown_table, dropdown_update)."""
    try:
        data = get("/api/workflows/n8n/status")
    except Exception as e:                                          # noqa: BLE001
        return (
            f"❌ Failed to reach backend: {e}",
            "",
            gr.update(choices=[], value=None),
        )

    if not data.get("configured"):
        return (
            f"⚠️ n8n not configured — {data.get('reason', 'set N8N_BASE_URL and N8N_API_KEY in .env')}",
            "",
            gr.update(choices=[], value=None),
        )

    ws = data.get("workflows", [])
    header = f"✅ Connected to n8n — {len(ws)} workflow(s) found"
    if not ws:
        return header, "_No workflows returned by n8n._", gr.update(choices=[], value=None)

    md = ["| ID | Name | Active | Trigger | Environment | Last Status | Success |",
          "|----|------|--------|---------|-------------|-------------|---------|"]
    dropdown_choices: list[tuple[str, str]] = []
    # Place On-Demand Webhook workflows at the top of the dropdown list
    for w in sorted(ws, key=lambda item: 0 if item.get("trigger_type") in ("n8n-nodes-base.webhook", "n8n-nodes-base.formTrigger") else 1):
        wid = str(w.get("id") or "-")
        name = w.get("name") or "(unnamed)"
        trig = w.get("trigger_type") or ""
        active = "yes" if w.get("active") else "no"
        md.append(
            f"| `{wid}` | {name} "
            f"| {active} "
            f"| {trig or '-'} "
            f"| {w.get('environment') or '-'} "
            f"| {w.get('last_execution_status') or '-'} "
            f"| {'yes' if w.get('success') else ('no' if w.get('success') is False else '-')} |"
        )
        badge = "⚡ [On-Demand]" if trig in ("n8n-nodes-base.webhook", "n8n-nodes-base.formTrigger") else "⏰ [Scheduled]"
        dropdown_choices.append((f"{badge} {name}  ·  {wid}", wid))

    return (
        header,
        "\n".join(md),
        gr.update(choices=dropdown_choices,
                  value=dropdown_choices[0][1] if dropdown_choices else None),
    )


def _test_connection() -> str:
    """Hit /api/workflows/n8n/ping — surfaces a red or green banner."""
    try:
        r: dict[str, Any] = get("/api/workflows/n8n/ping")
    except Exception as e:                                          # noqa: BLE001
        return f"❌ Failed to reach AIPP backend: {e}"

    if not r.get("configured"):
        return (
            f"⚠️ n8n not configured — {r.get('error', 'set N8N_BASE_URL / N8N_API_KEY')}"
        )
    if r.get("ok"):
        return (
            f"✅ Reached n8n at `{r.get('base_url')}` — "
            f"HTTP {r.get('status_code')} in {r.get('latency_ms')} ms"
        )
    return (
        f"❌ n8n unreachable at `{r.get('base_url')}` — "
        f"{r.get('error', 'unknown error')}"
    )


def _do_action(action: str, workflow_id: str, input_json: str = "") -> str:
    if not workflow_id:
        return "❌ Pick a workflow first."
    body: dict = {}
    if action == "execute" and input_json.strip():
        try:
            import json as _json
            parsed = _json.loads(input_json)
            body = {"input_data": parsed} if isinstance(parsed, dict) else {}
        except Exception as e:                                          # noqa: BLE001
            return f"❌ Input JSON is invalid: {e}"
    try:
        r = post(f"/api/workflows/n8n/{workflow_id}/{action}", json=body)
    except Exception as e:                                          # noqa: BLE001
        return f"❌ {e}"

    # `execute` returns a richer result (webhook URL, HTTP status, response body).
    if action == "execute" and r.get("ok"):
        inner = r.get("result", {}) or {}
        if inner.get("kind") == "webhook":
            body_preview = str(inner.get("response", ""))[:280]
            return (
                f"✅ Invoked webhook `{inner.get('method')} {inner.get('webhook_url')}` — "
                f"HTTP {inner.get('status_code')}\n\n"
                f"```json\n{body_preview}\n```\n\n"
                f"*Check the n8n Executions tab for the full run.*"
            )
        if inner.get("kind") == "unsupported_trigger":
            trigs = ", ".join(inner.get("trigger_types") or []) or "none detected"
            return (
                f"⚠️ Cannot execute on demand — this workflow uses `{trigs}`. "
                f"{inner.get('message', '')}"
            )
        if inner.get("kind") == "missing_webhook_path":
            return f"❌ {inner.get('message', 'Webhook trigger has no `path` set.')}"

    if r.get("ok"):
        return f"✅ `{action}` on `{workflow_id}` succeeded."
    return f"❌ `{action}` failed: {r}"


def _execute(workflow_id: str, input_json: str) -> str:
    return _do_action("execute", workflow_id, input_json)


def _activate(workflow_id: str) -> str:
    return _do_action("activate", workflow_id)


def _deactivate(workflow_id: str) -> str:
    return _do_action("deactivate", workflow_id)


def build_tab() -> None:
    with gr.Column():
        gr.Markdown(
            "### n8n Workflow Status\n"
            "AIPP does **not** bundle an n8n container — it integrates with "
            "your existing n8n instance via the REST API. Configure "
            "`N8N_BASE_URL` + `N8N_API_KEY` in `backend/.env`, then use the "
            "buttons below to inspect and drive your workflows.\n"
            "_All write actions (execute / activate / deactivate) are recorded "
            "in the **Audit Log** tab._"
        )
        with gr.Row():
            refresh = gr.Button("↻ Refresh workflows", variant="primary",
                                elem_id="n8n-refresh")
            test_btn = gr.Button("Test connection", elem_id="n8n-test-connection")
            auto_refresh = gr.Checkbox(
                label="Auto-refresh every 30 s",
                value=False,
                elem_id="n8n-auto-refresh",
                info="Live-poll the n8n API — handy during HITL demo runs.",
            )
        status_md = gr.Markdown(elem_id="n8n-status")
        conn_md = gr.Markdown(elem_id="n8n-connection")
        table = gr.Markdown(elem_id="n8n-table")

        gr.Markdown("### Trigger a workflow")
        with gr.Row():
            picker = gr.Dropdown(choices=[], label="Workflow",
                                  interactive=True, elem_id="n8n-picker")
        input_box = gr.Code(
            label="Input JSON (optional — passed as the webhook body)",
            language="json",
            value='{"text":"pod=coredns-xxxxx ns=kube-system"}',
            elem_id="n8n-execute-input",
        )
        with gr.Row():
            execute_btn = gr.Button("▶ Execute", variant="primary",
                                    elem_id="n8n-execute")
            activate_btn = gr.Button("Activate", elem_id="n8n-activate")
            deactivate_btn = gr.Button("Deactivate", elem_id="n8n-deactivate")
        action_result = gr.Markdown(elem_id="n8n-action-result")

        refresh.click(_refresh, outputs=[status_md, table, picker])
        test_btn.click(_test_connection, outputs=[conn_md])
        execute_btn.click(_execute, inputs=[picker, input_box], outputs=[action_result])
        activate_btn.click(_activate, inputs=[picker], outputs=[action_result])
        deactivate_btn.click(_deactivate, inputs=[picker], outputs=[action_result])

        # --- auto-refresh every 30 s while the checkbox is ticked ---------
        # gr.Timer.tick fires on the client-side; we gate it server-side by
        # checking the checkbox value so users can pause the loop without
        # tearing down the timer. Preserves the picker's current selection
        # so an in-progress "Execute" doesn't get its dropdown reset.
        def _tick(is_on: bool, current_pick):
            if not is_on:
                # Return `gr.update()` no-ops so nothing on-screen flickers.
                return gr.update(), gr.update(), gr.update()
            hdr, tbl, picker_update = _refresh()
            # Keep user's current selection if it's still in the choices.
            if current_pick and isinstance(picker_update, dict):
                choices = picker_update.get("choices") or []
                choice_values = [c[1] if isinstance(c, tuple) else c
                                 for c in choices]
                if current_pick in choice_values:
                    picker_update = gr.update(choices=choices, value=current_pick)
            return hdr, tbl, picker_update

        timer = gr.Timer(30.0)
        timer.tick(
            _tick,
            inputs=[auto_refresh, picker],
            outputs=[status_md, table, picker],
        )
