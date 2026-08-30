"""Gradio tab 2 — PipelineDoctor."""

from __future__ import annotations

import json
import os
import tempfile

import gradio as gr

from frontend.components.api_client import client

CI_PLATFORMS = ["azure_devops", "github_actions", "gitlab_ci", "harness", "tekton"]


def _analyze(ci_platform, incident, raw_log, log_file):
    files = {}
    data = {"ci_platform": ci_platform, "incident_context": incident or ""}
    if raw_log:
        data["raw_log"] = raw_log
    if log_file:
        # gradio uploads yield a path
        try:
            files = {"log_file": (os.path.basename(log_file), open(log_file, "rb"), "text/plain")}
        except Exception as e:
            return f"❌ cannot read uploaded file: {e}", "", gr.update(value=None, visible=False)
    try:
        r = client().post("/api/pipeline-doctor/analyze", data=data, files=files)
        if r.status_code >= 400:
            try:
                return f"❌ {r.json().get('detail', r.text)}", "", gr.update(value=None, visible=False)
            except Exception:
                return f"❌ {r.text}", "", gr.update(value=None, visible=False)
        report = r.json()
    except Exception as e:
        return f"❌ {e}", "", gr.update(value=None, visible=False)

    header = (
        f"### RCA — {report.get('failed_stage') or 'unknown stage'}\n"
        f"**Root cause:** {report.get('root_cause', '')}  \n"
        f"**Confidence:** {report.get('confidence', 0):.2f}"
    )

    md_parts = [header, "\n#### Evidence (from log)"]
    for ev in report.get("evidence", []):
        md_parts.append(f"- **{ev.get('line_range','')}** — {ev.get('interpretation','')}")
        md_parts.append(f"    ```\n    {ev.get('snippet','')}\n    ```")
    md_parts.append("\n#### Model Inferences (interpretation, not evidence)")
    for a in report.get("ai_inferences", []):
        md_parts.append(f"- {a}")
    md_parts.append("\n#### Corrective actions")
    for a in report.get("corrective_actions", []):
        md_parts.append(f"- {a}")
    md_parts.append("\n#### Preventive actions")
    for a in report.get("preventive_actions", []):
        md_parts.append(f"- {a}")

    # save as downloadable JSON
    tmp = tempfile.NamedTemporaryFile(prefix="rca_", suffix=".json", delete=False, mode="w", encoding="utf-8")
    json.dump(report, tmp, indent=2, default=str)
    tmp.close()

    return "✅ RCA generated", "\n".join(md_parts), gr.update(value=tmp.name, visible=True)


def build_tab():
    with gr.Column():
        gr.Markdown(
            "### PipelineDoctor\n"
            "Upload CI/CD logs or paste them and get an explainable root-cause analysis."
        )
        with gr.Row():
            ci_platform = gr.Dropdown(CI_PLATFORMS, label="CI/CD platform", value="github_actions",
                                      elem_id="pd-ci")
            log_file = gr.File(label="Upload log file (.log / .txt / .json)",
                               file_types=[".log", ".txt", ".json"], elem_id="pd-file")
        incident = gr.Textbox(label="Incident context (optional)", lines=2, elem_id="pd-incident")
        raw_log = gr.Textbox(label="Paste raw log (or upload above)", lines=10, elem_id="pd-raw")
        btn = gr.Button("Start Troubleshooting", variant="primary", elem_id="pd-analyze")
        status = gr.Markdown(elem_id="pd-status")
        report_md = gr.Markdown(elem_id="pd-report")
        download = gr.File(label="Download RCA JSON", visible=False, elem_id="pd-download")

        btn.click(_analyze,
                  inputs=[ci_platform, incident, raw_log, log_file],
                  outputs=[status, report_md, download])
