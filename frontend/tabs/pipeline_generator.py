"""Gradio tab 1 — Pipeline Generator + Commit.

Flow:
  1. User pastes repo URL + PAT, picks CI platform + cloud, optionally
     writes a custom requirement.
  2. Click Generate. Pipeline YAML appears in the tabs. Explanation and
     validation are also shown.
  3. Click Download to save the YAML locally.
  4. Choose a target branch from the dropdown (SAFETY: only branches that
     actually exist in the repo are shown).
  5. Click "Commit YAML to repo" to write the file to the chosen branch.
     From there, your CI/CD platform picks it up on the next push / PR.

Branch safety:
  - The commit endpoint refuses any branch that is not explicitly picked.
  - No branch is auto-selected. The user MUST click one before commit.
  - Refreshing the branch dropdown fetches the LIVE list from GitHub.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Tuple

import gradio as gr

from frontend.components.api_client import get, post, sse_post


CI_PLATFORMS = ["azure_devops", "github_actions", "gitlab_ci", "harness", "tekton"]
CLOUD_PLATFORMS = ["azure", "aws", "gcp"]
# Iteration-21: deployment targets. UI dropdown filters by selected cloud
# so the user can only pick a sensible target. "unspecified" is the safe
# default — the planner agent decides based on repo analysis.
DEPLOYMENT_TARGETS_BY_CLOUD: dict[str, list[tuple[str, str]]] = {
    "aws": [
        ("Let AIPP decide (recommended)",             "unspecified"),
        ("AWS EKS — managed Kubernetes",              "aws_eks"),
        ("AWS ECS Fargate — serverless containers",   "aws_ecs"),
        ("AWS Lambda — serverless functions",         "aws_lambda"),
        ("AWS App Runner — managed web apps",         "aws_app_runner"),
        ("AWS EC2 — single VM (SSM run-command)",     "aws_ec2"),
        ("AWS Auto Scaling Group — VMSS-equivalent",  "aws_asg"),
    ],
    "azure": [
        ("Let AIPP decide (recommended)",              "unspecified"),
        ("Azure AKS — managed Kubernetes",             "azure_aks"),
        ("Azure App Service — managed web apps",       "azure_webapp"),
        ("Azure Container Apps — serverless containers", "azure_container_apps"),
        ("Azure Functions — serverless functions",     "azure_functions"),
        ("Azure Virtual Machine — single VM",          "azure_vm"),
        ("Azure VM Scale Set (VMSS) — rolling upgrade", "azure_vmss"),
    ],
    "gcp": [
        ("Let AIPP decide (recommended)",              "unspecified"),
        ("Google GKE — managed Kubernetes",            "gcp_gke"),
        ("Google Cloud Run — serverless containers",   "gcp_cloud_run"),
        ("Google Cloud Functions — serverless functions", "gcp_cloud_functions"),
        ("Google App Engine — managed PaaS",           "gcp_app_engine"),
        ("Google Compute Engine — single VM",          "gcp_gce"),
        ("Google Managed Instance Group — rolling update", "gcp_mig"),
    ],
}
PIPELINE_TYPES = [
    ("All-in-one (CI + CD)", "all_in_one"),
    ("Build & Test only (no container push, no deploy)", "build_only"),
    ("CI only (build + test + security + container push)", "ci"),
    ("CD only (deploy an already-built image)", "cd"),
    ("Infra only (production Terraform: tflint + tfsec + OPA + Terratest + approval)", "infra"),
]


# 7 agents that run inside the LangGraph — kept in sync with
# backend/orchestrator/graph.py::AGENT_ORDER. If the backend adds another
# agent, this list should grow too.
_AGENT_ROWS = [
    ("repository_analysis",   "Repository analysis"),
    ("technology_detection",  "Technology detection"),
    ("architecture_detection", "Architecture detection"),
    ("pipeline_planning",     "Pipeline planning"),
    ("environment_deployment", "Environment strategy"),
    ("pipeline_generation",   "Pipeline YAML generation"),
    ("pipeline_validation",   "Validation"),
]


# Status → emoji-free unicode symbol so the UI stays readable in copy-paste
# transcripts and works fine when a screen reader announces it.
_STATUS_SYMBOL = {
    "pending": "○",
    "running": "◐",
    "done":    "●",
    "failed":  "✕",
}


def _render_progress(state: dict, llm_stream: str = "") -> str:
    """Render the 7-agent progress panel with the "Agentic Aura" HTML.

    Emits raw HTML rows styled by `frontend/static/aipp_theme.css`:
      - Running agents get a rotating conic orb + breathing shadow.
      - Done agents get a green tick.
      - Failed agents get a red exclamation.
      - Pending agents get a neutral outline.

    The live LLM output section is unchanged — still a Markdown fenced
    code block appended at the bottom.
    """
    total = len(_AGENT_ROWS)
    done_count = sum(
        1 for name, _label in _AGENT_ROWS
        if state.get(name, "pending") == "done"
    )
    pct = int(round(100 * done_count / total)) if total else 0

    html_parts = [
        "<div style='margin-bottom:8px; font-family: JetBrains Mono, monospace; color:#eaf0ff;'>",
        f"<b>{done_count}/{total} agents</b> · {pct}%",
        "</div>",
        "<div class='aipp-progress-strip'></div>",
        "<div style='height:12px'></div>",
    ]
    for i, (name, label) in enumerate(_AGENT_ROWS, start=1):
        s = state.get(name, "pending")
        detail = (state.get(f"{name}__detail", "") or "").replace("<", "&lt;")
        row_class = {
            "running": "aipp-agent-row aipp-agent-running",
            "done":    "aipp-agent-row aipp-agent-done",
            "failed":  "aipp-agent-row aipp-agent-failed",
        }.get(s, "aipp-agent-row")
        html_parts.append(
            f"<div class='{row_class}'>"
            f"<div class='aipp-agent-orb'></div>"
            f"<div class='aipp-agent-name'><b>{i}.</b> {label}</div>"
            f"<div class='aipp-agent-detail'>{s} · {detail}</div>"
            f"</div>"
        )
    md_tail = ""
    if llm_stream:
        tail = llm_stream[-1500:]
        md_tail = (
            "\n\n**Live LLM output** (last 1500 chars):\n```\n" + tail + "\n```"
        )
    return "\n".join(html_parts) + md_tail


def _render_usage_totals(totals: dict) -> str:
    """Render `/api/llm/usage` payload as a compact Markdown table."""
    calls = totals.get("total_calls", 0)
    tokens = totals.get("total_tokens", 0)
    cost = totals.get("estimated_cost_usd", 0.0)
    rows = [
        f"**Total calls:** {calls}  ·  "
        f"**Tokens:** {tokens:,}  ·  "
        f"**Estimated spend:** `${cost:.4f}`",
        "",
    ]
    by_model = totals.get("by_model", {})
    if by_model:
        rows.append("| Model | Calls | Prompt tok | Completion tok | Est. $ |")
        rows.append("|-------|------:|-----------:|---------------:|-------:|")
        for model, b in sorted(by_model.items()):
            rows.append(
                f"| `{model}` | {b['calls']} | "
                f"{b['prompt_tokens']:,} | {b['completion_tokens']:,} | "
                f"${b['cost_usd']:.4f} |"
            )
    else:
        rows.append("_No LLM calls yet. Generate a pipeline to populate._")
    rows.append("")
    rows.append("_" + totals.get("note", "Estimated.") + "_")
    return "\n".join(rows)


def _refresh_usage() -> str:
    try:
        return _render_usage_totals(get("/api/llm/usage"))
    except Exception as e:
        return f"⚠️ Could not fetch usage: {e}"


def _render_opa_preview(cloud: str) -> str:
    """Fetch the shipped OPA bundle and render only the selected cloud's rules.

    Powers the "OPA policy preview" accordion so users know exactly which
    Rego rules the `policy` stage of their infra pipeline will enforce —
    provided they copy the `/app/policy/<cloud>/*.rego` files into their
    own repo's `./policy/` folder. If no `.rego` files are shipped, the
    generated pipeline logs *"no policy dir — skipping"* and moves on.
    """
    try:
        payload = get("/api/policy/bundle") or {}
    except Exception as e:
        return f"⚠ Could not fetch OPA bundle: {e}"
    rules = (payload.get("clouds") or {}).get(cloud) or []
    if not rules:
        return f"_No shipped policies for `{cloud}` yet._"
    rows = [
        f"**{len(rules)} starter policies** for `{cloud}` — copy them into "
        f"your repo's `./policy/` folder to activate. AIPP's infra "
        f"pipelines auto-detect the folder and enforce `deny` rules.",
        "",
        "| Rule | Package | Purpose |",
        "|------|---------|---------|",
    ]
    for r in rules:
        rows.append(f"| `{r['file']}` | `{r['package']}` | {r['description']} |")
    return "\n".join(rows)


def _download_pipeline_yaml(yaml_text: str) -> gr.File:
    """Write generated YAML to downloadable file (.github/workflows/ci.yml or azure-pipelines.yml)."""
    if not yaml_text or not yaml_text.strip():
        return gr.update(visible=False)
    import os
    import tempfile
    filename = "azure-pipelines.yml" if ("trigger:" in yaml_text or "pool:" in yaml_text) else "ci.yml"
    tmp = tempfile.mkdtemp(prefix="aipp_pipeline_yaml_")
    path = os.path.join(tmp, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(yaml_text)
    return gr.update(value=path, visible=True)


def _reset_usage() -> str:
    try:
        post("/api/llm/usage/reset", json={})
        return _refresh_usage()
    except Exception as e:
        return f"⚠️ Could not reset usage: {e}"




# Cloud-specific Terraform provider + backend hints. AIPP standardises on
# Terraform for ALL supported clouds (AWS, Azure, GCP) — it is the only IaC
# tool that works cross-cloud and is what the pipeline generators expect.
# Bicep / CloudFormation / ARM templates are intentionally NOT emitted.
_INFRA_CLOUD_HINTS = {
    "aws": (
        "Target cloud is AWS. Use the `hashicorp/aws` Terraform provider, an "
        "S3 remote backend with DynamoDB state locking, and `aws-cli` for "
        "credential setup. Do NOT use CloudFormation, CDK, SAM, Bicep, ARM, "
        "or Pulumi."
    ),
    "azure": (
        "Target cloud is Azure. Use the `hashicorp/azurerm` Terraform provider "
        "and an azurerm remote backend (storage account + container). Do NOT "
        "use Bicep, ARM templates, or Pulumi — AIPP standardises on Terraform "
        "for cross-cloud parity."
    ),
    "gcp": (
        "Target cloud is GCP. Use the `hashicorp/google` Terraform provider "
        "and a GCS remote backend. Do NOT use Deployment Manager, Config "
        "Connector, Bicep, or Pulumi."
    ),
}


# Prepended directives that steer the Planning agent based on pipeline_type.
# Kept as literal English so a human can audit exactly what we tell the LLM.
_TYPE_DIRECTIVES = {
    "all_in_one": "",
    "build_only": (
        "PIPELINE TYPE: BUILD-AND-TEST-ONLY. Include ONLY the build, unit_test, "
        "sast, dependency_scan, code_quality and lint stages. Do NOT include "
        "container_build, container_scan, artifact_publish, or any deploy_* "
        "stage. This is the safest pipeline for a self-hosted agent that has no "
        "cloud registry access — nothing is pushed anywhere."
    ),
    "ci": (
        "PIPELINE TYPE: CI-ONLY. Include ONLY the build, unit_test, sast, "
        "dependency_scan, code_quality, container_build, container_scan and "
        "artifact_publish stages. Do NOT include any deploy_dev/qa/staging/prod "
        "stages. The pipeline stops after pushing the image to the registry."
    ),
    "cd": (
        "PIPELINE TYPE: CD-ONLY. Assume the container image was already built "
        "and pushed to the registry by a separate CI pipeline. Include ONLY the "
        "deploy_dev, deploy_qa, deploy_staging and deploy_prod stages. Do NOT "
        "include build/test/security/package stages."
    ),
    "infra": (
        "PIPELINE TYPE: INFRA-ONLY. Emit Terraform (`terraform init`, "
        "`terraform validate`, `terraform plan`, `terraform apply`) stages "
        "ONLY. Do NOT include any app build, unit_test, sast, dependency_scan, "
        "container_build, container_scan or deploy_* stages. AIPP mandates "
        "Terraform for infrastructure across ALL clouds (AWS, Azure, GCP) — "
        "you MUST NOT emit Bicep, ARM, CloudFormation, CDK, SAM, Pulumi, "
        "Deployment Manager, or any other IaC tool."
    ),
}


def _build_infra_directive(cloud: str, iac_tool: str = "terraform") -> str:
    """Compose the infra directive with a cloud-specific IaC hint.

    Iteration-20: when the caller explicitly opts into Bicep AND the cloud is
    Azure, swap the directive to Bicep-first guidance. On any other cloud
    the Bicep opt-in is ignored (Bicep is Azure-specific).
    """
    if (iac_tool or "").strip().lower() == "bicep" and cloud == "azure":
        return (
            "PIPELINE TYPE: INFRA-ONLY (Azure Bicep opt-in). Emit Bicep "
            "(`az deployment group create` / `az deployment sub create`) "
            "stages ONLY. Do NOT include app build, unit_test, sast, "
            "dependency_scan, container_build, container_scan or deploy_* "
            "stages. Use `az bicep build` + `az deployment group create` in "
            "the AzureRM service connection. Do NOT emit Terraform, ARM raw "
            "JSON, CloudFormation, CDK, SAM, Pulumi or Deployment Manager."
        )
    hint = _INFRA_CLOUD_HINTS.get(cloud, "")
    return f"{_TYPE_DIRECTIVES['infra']} {hint}".strip()


# ---------------------------------------------------------------------------
# Backend calls
# ---------------------------------------------------------------------------
def _build_merged_req(cloud, pipeline_type, custom_req, *, iac_tool: str = "terraform") -> str:
    """Compose the directive-prepended custom requirement string."""
    if pipeline_type == "infra":
        directive = _build_infra_directive(cloud or "aws", iac_tool=iac_tool)
    else:
        directive = _TYPE_DIRECTIVES.get(pipeline_type or "all_in_one", "")
    return ((directive + "\n\n" + (custom_req or "")).strip()
            if directive else (custom_req or ""))


def _initial_progress_state() -> dict:
    """Fresh per-agent status dictionary (all agents = pending)."""
    return {name: "pending" for name, _label in _AGENT_ROWS}


def _format_directive_trace(trace: dict | None) -> str:
    """Render the backend's `directive_trace` dict as a compact markdown
    panel. This is the UI-visible proof that the custom prompt was
    (a) recognised and (b) enforced in the emitted YAML."""
    if not trace or not (trace.get("directive_text") or "").strip():
        return (
            "_No custom deployment requirement was provided — pipeline "
            "generated with default (CLI-based) deploy tasks._"
        )

    ev = trace.get("yaml_evidence") or {}
    status = trace.get("enforcement_status", "unknown")
    matched = trace.get("matched_pattern")
    matched_row = f"`{matched}`" if matched else "_no match (handled via AI plan)_"
    ack = trace.get("llm_acknowledgement") or "_LLM planner returned no ack for this directive._"
    has_ack = ack and ack != "_LLM planner returned no ack for this directive._"

    status_icon = {
        "recognised_and_enforced": "✅",
        "handled_by_planner": "ℹ️",
        "recognised_but_no_yaml_change": "⚠️",
        "not_recognised": "ℹ️" if has_ack else "❌",
        "no_directive_provided": "—",
    }.get(status, "•")
    status_label = {
        "recognised_and_enforced":
            "Directive recognised AND enforced in the YAML.",
        "handled_by_planner":
            "Custom requirement evaluated and addressed by AI Planning Agent.",
        "recognised_but_no_yaml_change":
            "Directive recognised, but no deterministic YAML change was "
            "applied (likely: target cloud/CI has no Python-SDK path yet).",
        "not_recognised":
            "Custom requirement addressed by AI Planning Agent."
            if has_ack
            else "Directive did NOT match any parser rule — YAML uses defaults. See supported keywords below.",
        "no_directive_provided":
            "No directive was sent to the backend.",
    }.get(status, status)

    az_deploy = ev.get("az_cli_in_deploy_stage_count", 0)
    az_total = ev.get("az_cli_task_count", 0)
    az_ok = "✓ 0" if az_deploy == 0 else f"✗ {az_deploy}"
    py_ok = "✓" if ev.get("python_sdk_task_count", 0) > 0 else "✗"
    banner_ok = "✓" if ev.get("banner_present") else "✗"
    commit_ok = "✓" if ev.get("commit_scoped_image") else "✗"

    single_stage_val = ev.get("is_single_stage")
    single_stage_row = ""
    if single_stage_val is not None:
        single_stage_str = "✓ Single-stage (without multistage)" if single_stage_val else "Multi-stage"
        single_stage_row = f"| Pipeline layout | {single_stage_str} |\n"

    return (
        f"### {status_icon} Directive trace — {status_label}\n\n"
        f"**Your input:**\n\n> {trace.get('directive_text', '').strip()}\n\n"
        f"| Signal | Value |\n"
        f"|---|---|\n"
        f"| Directive matched | {matched_row} |\n"
        f"{single_stage_row}"
        f"| Parsed deploy style | `{trace.get('deploy_style', 'cli')}` |\n"
        f"| Header banner in YAML | {banner_ok} |\n"
        f"| `AzureCLI@2` tasks inside deploy stage (must be 0 for python style) | {az_ok} |\n"
        f"| `AzureCLI@2` tasks total (ACR login in package stage is OK) | {az_total} |\n"
        f"| Python-SDK task count (`UsePythonVersion@0` + `azure-identity`) | {py_ok} · {ev.get('python_sdk_task_count', 0)} |\n"
        f"| Image tag expression | `{ev.get('image_tag_expression') or '—'}` |\n"
        f"| Commit-scoped image tag | {commit_ok} |\n\n"
        f"**LLM planner acknowledgement:** {ack}\n\n"
        "<details><summary>Supported deterministic keywords the parser recognises</summary>\n\n"
        "- **Single-stage:** `without multistage`, `no multistage`, `single stage`, `single job`, `flat pipeline`\n"
        "- **Deploy style:** `no az cli`, `no azure cli`, `avoid az cli`, `without az cli`, `python only`, `python script`, `use python`\n\n"
        "*(Any other custom prompt is dynamically interpreted and shaped by the AI Planning Agent)*\n"
        "</details>"
    )


def _idle_outputs() -> tuple:
    """Placeholder outputs returned before the first backend event arrives."""
    return (
        "⏳ Starting agent pipeline…",
        _render_progress(_initial_progress_state()),
        "", "", "",
        gr.update(value=None, visible=False),
        gr.update(visible=False),
        "", "", "", "",
        gr.update(visible=False),
        "",  # directive_md
    )


def _error_outputs(message: str, progress_state: dict | None = None) -> tuple:
    return (
        f"❌ {message}",
        _render_progress(progress_state or _initial_progress_state()),
        "", "", "",
        gr.update(value=None, visible=False),
        gr.update(visible=False),
        "", "", "", "",
        gr.update(visible=False),
        "",  # directive_md
    )


def _final_outputs(res: dict, ci: str, repo_url: str,
                   progress_state: dict, pipeline_type: str) -> tuple:
    pipeline = res.get("pipeline", {}) or {}
    yaml_text = pipeline.get("yaml_content", "")
    filename = pipeline.get("filename", "pipeline.yml")

    explanation = res.get("explanation", "")
    plan_json = json.dumps(res.get("plan"), indent=2)
    validation_json = json.dumps(res.get("validation"), indent=2)

    tmp_dir = tempfile.mkdtemp(prefix="aipp_")
    safe_name = filename.replace("/", "_")
    path = os.path.join(tmp_dir, safe_name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(yaml_text)

    owner = res.get("analysis", {}).get("owner", "?")
    name = res.get("analysis", {}).get("name", "?")
    header = f"✅ Generated for {owner}/{name} — {res.get('generation_seconds', 0):.1f}s"
    directive_md = _format_directive_trace(res.get("directive_trace"))
    return (
        header,
        _render_progress(progress_state),
        yaml_text,
        explanation,
        plan_json + "\n\n---VALIDATION---\n" + validation_json,
        gr.update(value=path, visible=True),
        gr.update(visible=True),
        yaml_text,
        ci,
        repo_url.strip(),
        pipeline_type or "all_in_one",
        gr.update(visible=False),  # auto_deploy_panel hidden
        directive_md,
    )


def _generate(repo_url, pat, branch, ci, cloud, deployment_target, pipeline_type, agent_pool, iac_tool, custom_req):
    """Streaming generator: yields per-agent progress until final result.

    Gradio treats generator functions as progressive updates — each `yield`
    triggers a partial UI refresh so the user sees agents flip from ○ to ◐
    to ● in real time.
    """
    if not repo_url or not pat:
        yield _error_outputs("Please provide repo URL and PAT")
        return

    merged_req = _build_merged_req(cloud, pipeline_type, custom_req, iac_tool=iac_tool)
    body = {
        "repo_url": repo_url.strip(),
        "github_pat": pat.strip(),
        "branch": (branch or "main").strip(),
        "ci_platform": ci,
        "cloud_platform": cloud,
        "custom_requirement": merged_req,
        "pipeline_type": pipeline_type or "all_in_one",
        "agent_pool": (agent_pool or "").strip() or None,
        "iac_tool": (iac_tool or "terraform").strip().lower(),
        "deployment_target": (deployment_target or "unspecified").strip().lower(),
    }

    state = _initial_progress_state()
    llm_buffer = ""     # accumulates `kind="token"` deltas for live display
    yield _idle_outputs()

    result_payload: dict | None = None
    error_detail: str | None = None
    try:
        for event in sse_post("/api/pipelines/generate/stream", json_body=body):
            kind = event.get("kind")
            agent = event.get("agent")
            status = event.get("status")
            detail = event.get("detail", "")

            if kind == "token":
                # Live LLM output — append to the buffer and re-render the
                # progress panel with the tail visible under the agent table.
                llm_buffer += detail or ""
                yield (
                    "⏳ Streaming LLM response…",
                    _render_progress(state, llm_stream=llm_buffer),
                    "", "", "",
                    gr.update(value=None, visible=False),
                    gr.update(visible=False),
                    "", "", "", "",
                    gr.update(visible=False),
                    "",  # directive_md — 13th slot (iteration-26)
                )
            elif kind == "agent" and agent in state:
                state[agent] = status or state[agent]
                state[f"{agent}__detail"] = detail
                # New agent starting → reset the live buffer so we only
                # show tokens for the currently-running agent.
                if status == "running":
                    llm_buffer = ""
                yield (
                    "⏳ Running agent pipeline…",
                    _render_progress(state, llm_stream=llm_buffer),
                    "", "", "",
                    gr.update(value=None, visible=False),
                    gr.update(visible=False),
                    "", "", "", "",
                    gr.update(visible=False),
                    "",  # directive_md — 13th slot (iteration-26)
                )
            elif kind == "result":
                result_payload = event.get("payload") or {}
            elif kind == "error":
                error_detail = detail or "generation failed"
            elif kind == "done":
                break
    except Exception as e:
        yield _error_outputs(str(e), state)
        return

    if error_detail:
        yield _error_outputs(error_detail, state)
        return
    if not result_payload:
        yield _error_outputs("Backend closed the stream without a result", state)
        return

    yield _final_outputs(result_payload, ci, repo_url, state, pipeline_type)


def _list_branches(repo_url: str, pat: str):
    if not repo_url or not pat:
        return gr.update(choices=[], value=None), "❌ Provide repo URL and PAT first."
    try:
        res = get(
            "/api/deployment/branches",
            params={"repo_url": repo_url.strip(), "github_pat": pat.strip()},
        )
        branches = res.get("branches", [])
        if not branches:
            return gr.update(choices=[], value=None), "⚠️ No branches found."
        return gr.update(choices=branches, value=branches[0]), f"✅ {len(branches)} branches loaded."
    except Exception as e:
        return gr.update(choices=[], value=None), f"❌ {e}"


def _list_deploy_targets(token: str, ci_platform: str) -> tuple:
    """Return (choices, status_md) for the auto-deploy dropdown.

    Filters by CI platform so users can only pick a target that matches
    the pipeline they just generated (github_actions | azure_devops |
    gitlab_ci — additional platforms plug in trivially).
    """
    if not token:
        return gr.update(choices=[], value=None), "🔒 Sign in to enable auto-deploy."
    try:
        payload = get("/api/integrations/targets", token=token) or {}
    except Exception as e:
        return gr.update(choices=[], value=None), f"⚠ Could not load integrations: `{e}`"
    items = payload.get("targets", []) or []
    filtered = [t for t in items if t["platform"] == ci_platform]
    if not filtered:
        return (
            gr.update(choices=[], value=None),
            f"_No `{ci_platform}` integrations onboarded yet — head to the "
            "**Integrations** tab to add one._",
        )
    choices = [
        (f"{t['name']} · {t['repo_url']}", t["id"])
        for t in filtered
    ]
    return (
        gr.update(choices=choices, value=filtered[0]["id"]),
        f"✅ {len(filtered)} eligible target(s) loaded.",
    )


def _auto_deploy(token, target_id, ci, mode, branch, repo_url, yaml_text, message):
    if not token:
        return "🔒 Please sign in first."
    if not target_id:
        return "⚠ Pick a deployment target (or add one on the Integrations tab)."
    if not yaml_text:
        return "⚠ Generate a pipeline first."
    if not ci:
        return "⚠ CI platform is missing."
    if not (repo_url or "").strip():
        return ("⚠ Enter the **Deployment repo URL** — this is where the "
                "generated pipeline will be pushed.")
    try:
        r = post(
            "/api/integrations/deploy",
            token=token,
            json={
                "target_id": target_id,
                "ci_platform": ci,
                "yaml_content": yaml_text,
                "mode": mode or "pr",
                "branch": (branch or None),
                "repo_url": repo_url.strip(),
                "commit_message": message or None,
            },
        )
    except Exception as e:
        return f"❌ Auto-deploy failed: `{e}`"
    if r.get("action") == "pull_request":
        return (
            f"✅ **Pull request opened** — head branch `{r.get('head')}` → "
            f"base `{r.get('base')}`.\n\n"
            f"[Open PR]({r.get('pr_url')}) · "
            f"commit `{(r.get('commit_sha') or '')[:8]}`"
        )
    return (
        f"✅ **Committed** to `{r.get('branch')}`. "
        f"[View commit]({r.get('commit_url')}) · "
        f"`{(r.get('commit_sha') or '')[:8]}`"
    )


def _commit(repo_url, pat, target_branch, ci, yaml_text, message, pipeline_type):
    if not (repo_url and pat and target_branch and ci and yaml_text):
        return "❌ Missing input. Fill in the form and generate YAML first.", ""
    if not target_branch.strip():
        return "❌ Please select a target branch (safety check).", ""
    try:
        res = post("/api/deployment/commit", json={
            "repo_url": repo_url,
            "github_pat": pat.strip(),
            "target_branch": target_branch.strip(),
            "ci_platform": ci,
            "yaml_content": yaml_text,
            "commit_message": message or "chore(aipp): update CI/CD pipeline generated by AIPP",
        })
    except Exception as e:
        return f"❌ {e}", ""
    if not res.get("ok"):
        return f"❌ {res}", ""
    sha = (res.get("commit_sha") or "")[:8]
    action = res.get("action", "committed")
    url = res.get("commit_url", "")
    return (
        f"✅ **{action}** on branch `{target_branch}` — [{sha}]({url})",
        _setup_instructions(ci, target_branch, pipeline_type or "all_in_one"),
    )


def _setup_instructions(ci: str, branch: str, pipeline_type: str = "all_in_one") -> str:
    """One-time platform setup the user still needs to do outside AIPP.

    Adapts to the selected pipeline scope so the instructions don't ask the
    user to configure CD/infra items when they only asked for a CI pipeline
    (and vice versa).
    """
    # --- Build-only: safest scope; no cloud creds, no push, no deploy ---
    if pipeline_type == "build_only":
        return (
            f"### Build & Test only pipeline committed to `{branch}`\n\n"
            "This is the **safest scope** — the pipeline only builds the code, "
            "runs unit tests, and executes SAST + dependency + lint scans. "
            "Nothing is pushed to a registry, nothing is deployed.\n\n"
            "**Setup:** no service connections, no cloud credentials, no "
            "registry variables are needed. If you're running on a self-hosted "
            "agent (`pool: default` or your named pool), you're already good.\n\n"
            "If you're using Microsoft-hosted agents, you may still need to "
            "request a free parallelism grant at "
            "https://aka.ms/azpipelines-parallelism-request the first time."
        )

    # --- CI-only: no deploy variables, but ACR/ECR/GCR push still needs an SC ---
    if pipeline_type == "ci":
        if ci == "azure_devops":
            return (
                "### One-time Azure DevOps setup required for the CI pipeline\n\n"
                f"AIPP has committed `azure-pipelines.yml` to `{branch}`. This is a "
                "**CI-only** pipeline — it builds, tests, scans and pushes a container "
                "image to your registry. It does **not** deploy anywhere. Setup:\n\n"
                "1. **Create the pipeline** in ADO: `Pipelines` → `New Pipeline` → "
                "select GitHub → pick your repo → *Existing Azure Pipelines YAML "
                "file* → `/azure-pipelines.yml`\n"
                "2. **Create a service connection** to your Azure subscription — "
                "`Project settings` → `Service connections` → `New` → "
                "`Azure Resource Manager`. **Name it exactly** "
                "`azure-service-connection` (the pipeline parameter default). "
                "This is needed to `az acr login` before pushing the image; "
                "no deploy is performed.\n"
                "3. **Add one pipeline variable** — `REGISTRY_NAME` = your ACR "
                "name (e.g. `mycompanyacr`).\n"
                "4. **Run the pipeline**. Every push to a matching branch (develop, "
                f"release/*, main, tag v*.*.*) — and specifically your push to `{branch}` "
                "— will run build → test → scan → push image.\n\n"
                "_No subscription, resource group or Web App variables needed — "
                "those are only required by CD pipelines._"
            )
        if ci == "github_actions":
            return (
                "### One-time GitHub Actions setup required for the CI pipeline\n\n"
                f"AIPP has committed `.github/workflows/aipp-pipeline.yml` to `{branch}`. "
                "This is a **CI-only** pipeline — it builds, tests, scans and pushes an "
                "image. It does **not** deploy anywhere. Setup:\n\n"
                "Add these repository secrets in `Settings` → `Secrets and variables` → "
                "`Actions`:\n\n"
                "- `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` — container registry creds\n"
                "- `REGISTRY_URL` — e.g. `ghcr.io/<owner>` or `<acr>.azurecr.io`\n\n"
                "That's it. No cloud service principal or resource-group vars needed."
            )
        return (
            f"### CI-only pipeline committed to `{branch}`\n\n"
            f"AIPP wrote the pipeline for `{ci}`. It builds, tests, scans and "
            "pushes a container image. Configure only your **container registry** "
            "credentials in the platform — no cloud service principal needed."
        )

    # --- CD-only: assume the image already exists in the registry ---
    if pipeline_type == "cd":
        if ci == "azure_devops":
            return (
                "### One-time Azure DevOps setup required for the CD pipeline\n\n"
                f"AIPP has committed `azure-pipelines.yml` to `{branch}`. This is a "
                "**CD-only** pipeline — it deploys an image that was already built "
                "and pushed by a separate CI pipeline. Setup:\n\n"
                "1. **Create the pipeline** in ADO: `Pipelines` → `New Pipeline` → "
                "select GitHub → pick your repo → *Existing Azure Pipelines YAML "
                "file* → `/azure-pipelines.yml`\n"
                "2. **Create a service connection** to your Azure subscription — "
                "`Project settings` → `Service connections` → `New` → "
                "`Azure Resource Manager`. **Name it exactly** "
                "`azure-service-connection` (the pipeline parameter default), "
                "or override the parameter at queue time.\n"
                "3. **Add pipeline variables:**\n"
                "   - `IMAGE`, `TAG` = image already published by your CI pipeline\n"
                "   - `AZURE_WEBAPP_NAME` = your Azure Web App name (deploy target)\n"
                "   - `AZURE_RG` = the resource group containing the Web App\n"
                "4. **Create environments** in ADO: `Pipelines` → `Environments` → "
                "create `development`, `qa`, `staging`, `production`. Add an "
                "approval check on `production`.\n"
                "5. **Trigger** by pushing to the branch or clicking below.\n\n"
                "_Build/test/scan setup is not required — that lives in your CI pipeline._"
            )
        if ci == "github_actions":
            return (
                "### One-time GitHub Actions setup required for the CD pipeline\n\n"
                f"AIPP has committed `.github/workflows/aipp-pipeline.yml` to `{branch}`. "
                "This is a **CD-only** pipeline. Add these repository secrets in "
                "`Settings` → `Secrets and variables` → `Actions`:\n\n"
                "- `AZURE_CREDENTIALS` (or `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`, "
                "or `GCP_SA_KEY`)\n"
                "- `IMAGE`, `TAG` — the image your CI pipeline already published\n"
                "- Environment protection rules on `production` (Settings → "
                "Environments → New environment → require reviewers)\n"
            )
        return (
            f"### CD-only pipeline committed to `{branch}`\n\n"
            f"Configure cloud credentials for `{ci}` and set `IMAGE` + `TAG` to "
            "point at the artifact published by your CI pipeline."
        )

    # --- Infra-only: Terraform state backend + cloud auth ---
    if pipeline_type == "infra":
        return (
            f"### One-time setup required for the production Terraform pipeline\n\n"
            f"AIPP committed a **5-stage production-grade Terraform pipeline** "
            f"to `{branch}`:\n\n"
            "1. **validate** — `terraform fmt -check` + `init` + `validate` "
            "+ **tflint** + **tfsec**\n"
            "2. **plan** — produces a `tfplan` artifact + `plan.json` + `plan.txt`\n"
            "3. **policy** — OPA / **conftest** gate against the plan + "
            "optional **Terratest** suite\n"
            "4. **apply** — deployment job **behind a manual approval** on the "
            "`production` environment; consumes the plan artifact (no re-plan)\n"
            "5. **outputs** — publishes `terraform output -json` as an artifact\n\n"
            "Setup:\n"
            "1. **Terraform state backend** — create the remote store once:\n"
            "   - AWS → S3 bucket + DynamoDB lock table\n"
            "   - Azure → storage account + container\n"
            "   - GCP → GCS bucket\n"
            "2. **Service connection** — Azure Resource Manager (or AWS / GCP "
            "equivalent) named exactly `azure-service-connection` "
            "(or `aws-service-connection` / `gcp-service-connection`). This is "
            "the compile-time SC that all `terraform` commands run under.\n"
            "3. **Pipeline variables** (or a variable group):\n"
            "   - `TF_ROOT` — path to your `.tf` files (default `.`)\n"
            "   - `TF_VERSION` — pinned Terraform version, e.g. `1.9.5` (default `latest`)\n"
            "   - `TF_BACKEND_KEY` — path in the remote backend (default `<repo>.tfstate`)\n"
            "   - Backend-specific vars — e.g. for Azure: `RESOURCE_GROUP_NAME`, "
            "`STORAGE_ACCOUNT_NAME`, `CONTAINER_NAME`; for AWS: `TF_STATE_BUCKET`, "
            "`TF_LOCK_TABLE`\n"
            "4. **Environment approval** — `Pipelines` → `Environments` → "
            "`production` → `Approvals and checks` → add yourself as approver. "
            "This blocks stage 4 (`apply`) until a human clicks approve.\n"
            "5. **OPA policies (optional)** — drop `.rego` files under `./policy/` "
            "in the repo. Absent → stage 3 skips the gate cleanly.\n"
            "6. **Terratest (optional)** — drop `_test.go` files under `./tests/`. "
            "Absent → stage 3 skips the Terratest step cleanly.\n\n"
            "_This pipeline is safe by default — no `apply` runs without approval; "
            "plan/policy/apply consume the same immutable artifact._"
        )

    # --- All-in-one (default) — original CI+CD instructions ---
    if ci == "azure_devops":
        return (
            "### One-time Azure DevOps setup required for CD to actually run\n\n"
            "AIPP has committed `azure-pipelines.yml` to your repo. For the pipeline "
            "to actually build and deploy, you need these one-time items in Azure DevOps:\n\n"
            "1. **Create the pipeline** in ADO: `Pipelines` → `New Pipeline` → select GitHub → "
            "pick your repo → choose *Existing Azure Pipelines YAML file* → `/azure-pipelines.yml`\n"
            "2. **Create a service connection** to your Azure subscription — "
            "`Project settings` → `Service connections` → `New` → `Azure Resource "
            "Manager`. **Name it exactly** `azure-service-connection` (this is "
            "the default of the pipeline's `azureServiceConnection` parameter). "
            "If you use a different name, override the parameter every time "
            "you queue the pipeline.\n"
            "3. **Create pipeline variables** (or a variable group) with these keys:\n"
            "   - `REGISTRY_NAME` = your ACR name (e.g. `mycompanyacr`)\n"
            "   - `AZURE_WEBAPP_NAME` = your Azure Web App name (target of the deploy)\n"
            "   - `AZURE_RG` = the resource group containing the Web App and ACR\n"
            "4. **Create the target environments** in ADO: `Pipelines` → `Environments` → "
            "create `development`, `qa`, `staging`, `production`. On `production`, add an "
            "approval check (`Approvals and checks` → `Approvals` → add yourself).\n"
            "5. **Run the pipeline**. From now on, every push to a matching branch (develop, "
            f"release/*, main, tag v*.*.*) — and specifically your push to `{branch}` — will "
            "trigger the CI/CD flow automatically.\n\n"
            "_You only do steps 1-4 once per project. Step 5 (running) is automatic on push._"
        )
    if ci == "github_actions":
        return (
            "### One-time GitHub Actions setup required for CD to actually run\n\n"
            "AIPP has committed `.github/workflows/aipp-pipeline.yml`. For deploys to work, "
            "add these repository secrets in `Settings` → `Secrets and variables` → `Actions`:\n\n"
            "- `AZURE_CREDENTIALS` (or `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`, or `GCP_SA_KEY`)\n"
            "- `REGISTRY_NAME`, `ACR_USERNAME`, `ACR_PASSWORD` (if using Azure)\n"
            "- `IMAGE`, `TAG` — set automatically by the pipeline\n\n"
            "Then push to the matching branch to fire the workflow."
        )
    return (
        "### Setup notes\n\n"
        f"AIPP committed the pipeline file to `{branch}`. "
        f"Please refer to your `{ci}` platform docs for the exact secrets and service "
        "connections required."
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def build_tab(token_state: "gr.State | None" = None):
    with gr.Column():
        gr.Markdown(
            "### Pipeline Generator\n"
            "Analyze a real GitHub repository and generate an explainable, "
            "deployment-ready CI/CD pipeline.\n"
            "_PAT is used read-only during generation. A separate button is "
            "used for committing changes back to your repo._"
        )
        with gr.Row():
            repo_url = gr.Textbox(label="GitHub repository URL",
                                  placeholder="https://github.com/owner/name",
                                  elem_id="pg-repo-url")
            branch = gr.Textbox(label="Analysis branch (read-only)", value="main",
                                elem_id="pg-branch")
        pat = gr.Textbox(label="GitHub PAT", type="password",
                         info=("Read-only PAT is enough — AIPP uses it ONLY to "
                               "read the repo. For pushing the generated pipeline "
                               "back, onboard a deployment repo on the "
                               "**Integrations** tab with a separate write-scoped PAT."),
                         elem_id="pg-pat")
        with gr.Row():
            ci = gr.Dropdown(CI_PLATFORMS, label="CI/CD Platform",
                             value="github_actions", elem_id="pg-ci")
            cloud = gr.Dropdown(CLOUD_PLATFORMS, label="Cloud Platform",
                                value="azure", elem_id="pg-cloud")
        # Iteration-21: deployment target inside the chosen cloud. Filtered
        # by the currently-selected cloud so users can only pick sensible
        # options (e.g. EKS is only offered when cloud=aws).
        deployment_target = gr.State("unspecified")
        pipeline_type = gr.Radio(
            choices=[(label, val) for label, val in PIPELINE_TYPES],
            value="all_in_one",
            label="Pipeline scope",
            info="Build-only skips container push and deploy — safest for self-hosted agents without cloud creds.",
            elem_id="pg-pipeline-type",
        )
        agent_pool = gr.Textbox(
            label="Agent pool / runner label (optional)",
            placeholder="Leave blank for cloud-hosted runners. "
                        "Type e.g. `default`, `AIPP-Agents` or your GitHub self-hosted label to run on your own hardware.",
            info="Applies to Azure DevOps (pool name), GitHub Actions (self-hosted runner label) and GitLab CI (job tag).",
            elem_id="pg-agent-pool",
        )
        # Iteration-20: opt-in IaC selector. Default = Terraform for ALL
        # clouds. `bicep` is only honoured for Azure; on AWS/GCP the backend
        # falls back to Terraform silently.
        iac_tool = gr.Dropdown(
            choices=[("Terraform (default, all clouds)", "terraform"),
                     ("Bicep (Azure only, opt-in)", "bicep")],
            value="terraform",
            label="Infra-as-Code tool",
            info="AIPP standardises on Terraform for cross-cloud parity. "
                 "Select Bicep ONLY if you want Azure-native ARM templating "
                 "and your target cloud is Azure — otherwise this is ignored.",
            elem_id="pg-iac-tool",
        )
        custom_req = gr.Textbox(
            label="Custom deployment requirement (optional)",
            placeholder=(
                "Leave blank to use the AIPP standard 6-gate pipeline: "
                "Build → Unit test → SAST → Dep scan → Lint → Container build+scan+push → "
                "Deploy Dev/QA/Staging (auto) → Deploy Prod (approval). "
                "Or override: e.g. 'deploy to AKS with Helm, skip Trivy, use canary for prod'"
            ),
            lines=3,
            elem_id="pg-custom",
        )
        btn = gr.Button("Generate Pipeline", variant="primary", elem_id="pg-generate")

        header = gr.Markdown(elem_id="pg-header")

        # ---- Per-agent progress panel (streaming SSE) ----
        with gr.Accordion("Agent progress (live)", open=True,
                          elem_id="pg-progress-accordion"):
            progress_md = gr.Markdown(
                value=_render_progress(_initial_progress_state()),
                elem_id="pg-progress",
            )

        # ---- LLM usage / spend meter ----
        with gr.Accordion("LLM usage & estimated spend", open=False,
                          elem_id="pg-llm-usage-accordion"):
            usage_md = gr.Markdown(
                value=_render_usage_totals({"total_calls": 0,
                                            "total_tokens": 0,
                                            "estimated_cost_usd": 0.0,
                                            "by_model": {}}),
                elem_id="pg-llm-usage",
            )
            with gr.Row():
                refresh_usage_btn = gr.Button("Refresh usage",
                                              elem_id="pg-usage-refresh")
                reset_usage_btn = gr.Button("Reset counters",
                                             variant="secondary",
                                             elem_id="pg-usage-reset")

        # Iteration-25 note: previously used a nested `gr.Tabs()` to switch
        # between YAML / Explanation / Plan panels, but Gradio 4.44.1 crashes
        # with "Cannot read properties of undefined (reading 'indexOf')" the
        # instant a Tabs component is nested inside another Tab. We use
        # collapsible Accordions instead — same UX, zero Svelte crashes.
        with gr.Accordion("Generated YAML", open=True, elem_id="pg-acc-yaml"):
            yaml_out = gr.Code(language="yaml", label="Generated pipeline",
                               elem_id="pg-yaml")
            download_yaml_btn = gr.Button("⬇ Download Pipeline YAML (.yml)", variant="primary", elem_id="pg-download-yaml-btn")
            download_file = gr.File(label="ci.yml", visible=False, elem_id="pg-download-file")
            download_yaml_btn.click(_download_pipeline_yaml, inputs=[yaml_out], outputs=[download_file])
        with gr.Accordion(
            "Directive trace — was my custom prompt recognised & enforced?",
            open=True, elem_id="pg-acc-directive",
        ):
            directive_md = gr.Markdown(
                elem_id="pg-directive-trace",
                value=(
                    "_Fill the Custom deployment requirement above and click "
                    "Generate — this panel will show whether your directive was "
                    "recognised by the parser and how it was enforced in the "
                    "emitted YAML._"
                ),
            )
        with gr.Accordion("Explanation", open=False, elem_id="pg-acc-exp"):
            exp = gr.Markdown(elem_id="pg-explanation")
        with gr.Accordion("Plan & Validation (JSON)", open=False, elem_id="pg-acc-plan"):
            plan = gr.Code(language="json", label="Plan and validation report",
                           elem_id="pg-plan")
        download = gr.File(label="Download YAML", visible=False, elem_id="pg-download")

        # Hidden state used by the Commit/Deploy section
        yaml_state = gr.State("")
        ci_state = gr.State("")
        repo_url_state = gr.State("")
        pipeline_type_state = gr.State("all_in_one")

        # ---- Commit & Deploy panel (hidden until pipeline is generated) ----
        # Iteration-26.6 · This panel is now the LEGACY path — it uses the
        # developer PAT which by design is read-only. We keep it for teams
        # whose developer token happens to have `Contents: Write` scope, but
        # the primary flow moved to `auto_deploy_panel` below (Integrations-
        # backed write-scoped tokens on a separate deployment repository).
        with gr.Group(visible=False, elem_id="pg-deploy-panel") as deploy_panel:
            with gr.Accordion(
                "🚀 Commit to Deployment Repository (Write Access PAT)",
                open=True,
                elem_id="pg-deploy-acc",
            ):
                gr.Markdown(
                    "Specify your target **Deployment Repository URL** and a **Write-scoped PAT** (`Contents: Write`) to commit the generated CI/CD YAML directly to your repository."
                )
                with gr.Row():
                    deploy_repo_url = gr.Textbox(
                        label="Deployment Repository URL",
                        placeholder="https://github.com/my-org/deploy-pipelines",
                        elem_id="pg-deploy-repo-url",
                    )
                    write_pat = gr.Textbox(
                        label="Deployment Write PAT",
                        type="password",
                        placeholder="ghp_...",
                        info="Write-scoped Personal Access Token (Contents: Write)",
                        elem_id="pg-write-pat",
                    )
                with gr.Row():
                    refresh_branches_btn = gr.Button("↻ Load target branches",
                                                     elem_id="pg-load-branches")
                    target_branch = gr.Dropdown(
                        choices=[], label="Target branch (mandatory)",
                        interactive=True, elem_id="pg-target-branch",
                    )
                branches_status = gr.Markdown(elem_id="pg-branches-status")
                commit_msg = gr.Textbox(
                    label="Commit Message",
                    value="chore(aipp): update CI/CD pipeline generated by AIPP",
                    elem_id="pg-commit-msg",
                )
                commit_btn = gr.Button("🚀 Commit YAML to Repository",
                                       variant="primary",
                                       elem_id="pg-commit")
                commit_result = gr.Markdown(elem_id="pg-commit-result")
                setup_help = gr.Markdown(elem_id="pg-setup-help")

        # ---- Auto-Deploy panel (Iteration-25 · PRIMARY PATH after Iteration-26.6) ----
        with gr.Group(visible=False, elem_id="pg-auto-deploy-panel") as auto_deploy_panel:
            gr.Markdown(
                "### 📦 Deliver this pipeline\n"
                "**Recommended flow:** onboard a **deployment repository** on "
                "the **Integrations** tab (with a WRITE-scoped PAT stored "
                "encrypted server-side), then push the generated YAML there "
                "from here. Your developer PAT stays **read-only** — AIPP "
                "never asks it for write access.\n\n"
                "**Deploy mode**\n"
                "• `Pull request` (recommended) — AIPP creates a branch on the "
                "deployment repo and opens a PR you review + merge.\n"
                "• `Direct commit` — commits straight to the base branch "
                "(must already exist)."
            )
            deploy_choice = gr.Radio(
                choices=[("I'll download and push manually", "manual"),
                         ("Auto-push via AIPP (uses a saved integration)", "auto")],
                value="auto",
                label="How do you want to deliver this pipeline?",
                elem_id="pg-deploy-choice",
            )
            with gr.Group(visible=True, elem_id="pg-auto-deploy-inner") as auto_inner:
                with gr.Row():
                    load_targets_btn = gr.Button("↻ Load my integrations",
                                                 elem_id="pg-load-targets")
                    ad_target = gr.Dropdown(
                        choices=[], label="Saved deployment target",
                        elem_id="pg-ad-target",
                    )
                targets_status = gr.Markdown(elem_id="pg-ad-status")
                with gr.Row():
                    ad_repo_url = gr.Textbox(
                        label="Deployment repo URL",
                        placeholder="https://github.com/my-org/deploy-pipelines",
                        info=("Pick the target repo at push time. Overrides "
                              "any default saved on the integration."),
                        elem_id="pg-ad-repo-url",
                    )
                    ad_branch = gr.Textbox(
                        label="Base branch",
                        value="main",
                        placeholder="main",
                        elem_id="pg-ad-branch",
                    )
                ad_mode = gr.Radio(
                    choices=[("Pull request (safest)", "pr"),
                             ("Direct commit (advanced)", "commit")],
                    value="pr",
                    label="Deploy mode",
                    elem_id="pg-ad-mode",
                )
                ad_msg = gr.Textbox(
                    label="Commit / PR message",
                    value="chore(aipp): update CI/CD pipeline generated by AIPP",
                    elem_id="pg-ad-msg",
                )
                confirm_check = gr.Checkbox(
                    label="I confirm this will write to the selected deployment repo.",
                    value=False,
                    elem_id="pg-ad-confirm",
                )
                deploy_btn = gr.Button("🚀 Confirm & auto-deploy",
                                       variant="primary", interactive=False,
                                       elem_id="pg-ad-deploy")
                deploy_result = gr.Markdown(elem_id="pg-ad-result")

        # ---- OPA Live Preview (which policy rules WILL fire for this cloud) ----
        with gr.Accordion("OPA policy preview (which gates will fire)",
                          open=False, elem_id="pg-opa-accordion"):
            opa_md = gr.Markdown(
                value=_render_opa_preview("azure"),
                elem_id="pg-opa-preview",
            )
        cloud.change(
            lambda c: _render_opa_preview(c),
            inputs=[cloud],
            outputs=[opa_md],
        )

        # ---- wiring ----

        btn.click(
            _generate,
            inputs=[repo_url, pat, branch, ci, cloud, deployment_target,
                    pipeline_type, agent_pool, iac_tool, custom_req],
            outputs=[header, progress_md, yaml_out, exp, plan, download,
                     deploy_panel, yaml_state, ci_state, repo_url_state,
                     pipeline_type_state, auto_deploy_panel, directive_md],
        )
        # Auto-refresh usage AFTER a generation finishes so the badge stays
        # in sync without the user having to click "Refresh usage" manually.
        btn.click(_refresh_usage, inputs=None, outputs=[usage_md])
        refresh_usage_btn.click(_refresh_usage, inputs=None, outputs=[usage_md])
        reset_usage_btn.click(_reset_usage, inputs=None, outputs=[usage_md])
        refresh_branches_btn.click(
            _list_branches,
            inputs=[deploy_repo_url, write_pat],
            outputs=[target_branch, branches_status],
        )
        commit_btn.click(
            _commit,
            inputs=[deploy_repo_url, write_pat, target_branch, ci_state, yaml_state,
                    commit_msg, pipeline_type_state],
            outputs=[commit_result, setup_help],
        )

        # ---- Auto-Deploy wiring ----
        deploy_choice.change(
            lambda c: gr.update(visible=(c == "auto")),
            inputs=[deploy_choice], outputs=[auto_inner],
        )
        if token_state is not None:
            load_targets_btn.click(
                _list_deploy_targets,
                inputs=[token_state, ci_state],
                outputs=[ad_target, targets_status],
            )
            confirm_check.change(
                lambda v: gr.update(interactive=bool(v)),
                inputs=[confirm_check], outputs=[deploy_btn],
            )
            deploy_btn.click(
                _auto_deploy,
                inputs=[token_state, ad_target, ci_state, ad_mode, ad_branch,
                        ad_repo_url, yaml_state, ad_msg],
                outputs=[deploy_result],
            )
