"""Batch Repo Runner — thesis-benchmark UI.

Iteration-26.

Runs pipeline generation across many GitHub repositories with a common
configuration. Persists one `ResearchExperiment` row per repo so the MS
thesis Evaluation chapter can plot generation seconds, validation-pass
rate, YAML size, secret-scan cleanliness, etc.

UX contract:
  * User pastes N repo URLs (one per line, max 20 per batch).
  * A single PAT is used for every repo (must have `repo` read access).
  * CI + Cloud + pipeline_type + IaC tool are shared across the batch.
  * Repos are processed sequentially by the backend so LLM quota is
    honoured and per-repo failures don't abort the batch.
  * Results appear as a DataFrame and can be downloaded as CSV for the
    thesis' benchmark table.

Gradio 4.44.1 note: DO NOT make synchronous API calls at build time inside
this tab. All fetches must be triggered by user clicks.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile

import gradio as gr
import pandas as pd

from frontend.components.api_client import post


CI_PLATFORMS = ["azure_devops", "github_actions", "gitlab_ci", "harness", "tekton"]
CLOUD_PLATFORMS = ["azure", "aws", "gcp"]
PIPELINE_TYPES = [
    ("All-in-one (CI + CD)", "all_in_one"),
    ("Build & test only", "build_test"),
    ("CI only (+ security + push)", "ci_only"),
    ("CD only (deploy existing image)", "cd_only"),
    ("Infra only (Terraform + policy gates)", "infra_only"),
]
IAC_TOOLS = [
    ("Terraform (default, all clouds)", "terraform"),
    ("Bicep (Azure only, opt-in)", "bicep"),
]

MAX_REPOS = 20

EMPTY_TABLE = pd.DataFrame(
    columns=[
        "#", "repo_url", "branch", "status", "seconds",
        "validation_passed", "yaml_bytes", "secrets_clean",
        "deployment_target", "error",
    ]
)

# Chart schema — one row per repo. Gradio 4.44's `BarPlot` crashes on
# empty-with-no-value mounts, so we ship a schema-only DataFrame at build
# time and populate on Run.
EMPTY_CHART = pd.DataFrame(columns=["repo", "seconds", "outcome"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_repos(text: str) -> list[dict]:
    """Turn a textarea into a `[{repo_url, branch}, ...]` list.

    Each non-empty line is one repo. Optional `@branch` suffix picks the
    branch, otherwise defaults to `main`. Blank lines and `#` comments are
    ignored.
    """
    items: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        branch = "main"
        if "@" in line and line.rsplit("@", 1)[1].strip():
            url, branch = line.rsplit("@", 1)
            line = url.strip()
            branch = branch.strip() or "main"
        if line.startswith(("http://", "https://")) and "github.com" in line:
            items.append({"repo_url": line, "branch": branch})
    # De-duplicate while preserving order.
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for it in items:
        key = (it["repo_url"], it["branch"])
        if key not in seen:
            seen.add(key)
            unique.append(it)
    return unique


def _results_to_df(results: list[dict]) -> pd.DataFrame:
    if not results:
        return EMPTY_TABLE.copy()
    rows = []
    for i, r in enumerate(results, start=1):
        rows.append({
            "#": i,
            "repo_url": r.get("repo_url", ""),
            "branch": r.get("branch", "main"),
            "status": r.get("status", ""),
            "seconds": r.get("seconds", 0),
            "validation_passed": r.get("validation_passed"),
            "yaml_bytes": r.get("yaml_bytes", 0),
            "secrets_clean": r.get("secrets_clean"),
            "deployment_target": r.get("deployment_target", ""),
            "error": (r.get("error") or "")[:200],
        })
    return pd.DataFrame(rows)


def _results_to_chart(results: list[dict]) -> pd.DataFrame:
    """Project batch results into the shape `gr.BarPlot` expects.

    Rows: `repo` (short label like `owner/name`), `seconds`, `outcome`
    (one of `passed`, `failed_validation`, `error`). Outcome drives the
    bar colour so users can eyeball the pass rate at a glance.
    """
    if not results:
        return EMPTY_CHART.copy()
    rows = []
    for r in results:
        url = r.get("repo_url") or ""
        short = url.rsplit("/", 2)[-2:] if "/" in url else [url]
        label = "/".join(short) if len(short) == 2 else url
        if r.get("status") != "ok":
            outcome = "error"
        elif r.get("validation_passed"):
            outcome = "passed"
        else:
            outcome = "failed_validation"
        rows.append({
            "repo": label,
            "seconds": float(r.get("seconds") or 0),
            "outcome": outcome,
        })
    return pd.DataFrame(rows)


def _df_to_csv_path(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None
    fd, path = tempfile.mkstemp(prefix="aipp_batch_", suffix=".csv")
    os.close(fd)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return path


def _summary_md(payload: dict) -> str:
    total = payload.get("total", 0)
    ok = payload.get("ok", 0)
    failed = payload.get("failed", 0)
    avg = payload.get("avg_seconds", 0.0)
    total_s = payload.get("total_seconds", 0.0)
    pass_rate = (ok / total * 100.0) if total else 0.0
    return (
        f"**Batch complete** — {ok}/{total} succeeded ({pass_rate:.1f}%), "
        f"{failed} failed.  \n"
        f"Total wall-time: **{total_s:.2f}s** · Avg per-repo: **{avg:.2f}s**"
    )


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------
def _run_batch(repos_text, pat, ci, cloud, pipeline_type, iac_tool,
               experiment_label, token):
    if not token:
        return ("⚠ Please sign in first.", EMPTY_TABLE.copy(),
                EMPTY_CHART.copy(), None)
    repos = _parse_repos(repos_text)
    if not repos:
        return (
            "⚠ Paste at least one **github.com** repo URL (one per line). "
            "Add `@branch` after the URL to pick a non-main branch.",
            EMPTY_TABLE.copy(),
            EMPTY_CHART.copy(),
            None,
        )
    if len(repos) > MAX_REPOS:
        return (
            f"⚠ At most {MAX_REPOS} repos per batch — you submitted "
            f"{len(repos)}. Trim the list and retry.",
            EMPTY_TABLE.copy(),
            EMPTY_CHART.copy(),
            None,
        )
    if not pat or len(pat.strip()) < 8:
        return ("⚠ A GitHub PAT with `repo` read access is required.",
                EMPTY_TABLE.copy(), EMPTY_CHART.copy(), None)
    body = {
        "repos": repos,
        "github_pat": pat.strip(),
        "ci_platform": ci,
        "cloud_platform": cloud,
        "pipeline_type": pipeline_type,
        "iac_tool": iac_tool,
        "deployment_target": "unspecified",
        "experiment_label": (experiment_label or "aipp").strip() or "aipp",
    }
    try:
        # Batch runs are long — bump the client timeout via the shared
        # httpx client's 300s default. See frontend/components/api_client.
        resp = post("/api/research/batch", json=body, token=token)
    except Exception as e:
        return (f"❌ Batch request failed: `{e}`", EMPTY_TABLE.copy(),
                EMPTY_CHART.copy(), None)
    results = resp.get("results", [])
    df = _results_to_df(results)
    chart_df = _results_to_chart(results)
    return (_summary_md(resp), df, chart_df, None)


def _download_csv(df: pd.DataFrame):
    path = _df_to_csv_path(df)
    if not path:
        return None
    return path


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def build_tab(token_state: gr.State) -> None:
    with gr.Column():
        gr.Markdown(
            "## Batch Repo Runner\n"
            "Score-run **up to 20 GitHub repositories** with a shared "
            "configuration. Every repo is recorded as a "
            "`ResearchExperiment` row so you can compare AIPP against "
            "static templates or generic-LLM baselines in the thesis "
            "Evaluation chapter. Failures do NOT abort the batch — each "
            "repo's status is captured in the results table."
        )

        with gr.Group():
            gr.Markdown("### 1. Repositories")
            repos_in = gr.Textbox(
                label="GitHub repo URLs (one per line, optional `@branch`)",
                placeholder=(
                    "https://github.com/octocat/hello-world\n"
                    "https://github.com/psf/requests@main\n"
                    "# lines starting with # are ignored"
                ),
                lines=8,
                elem_id="batch-repos",
            )
            pat_in = gr.Textbox(
                label="GitHub PAT (read-only is enough)",
                type="password",
                info=("Same token used for every repo in the batch. "
                      "`repo` scope is sufficient for private repos."),
                elem_id="batch-pat",
            )
            exp_in = gr.Textbox(
                label="Experiment label",
                value="aipp",
                info=("Tag written to `ResearchExperiment.experiment_type`. "
                      "Use e.g. `aipp`, `static_template`, `generic_llm` so "
                      "your thesis benchmarks are easy to filter."),
                elem_id="batch-exp",
            )

        with gr.Group():
            gr.Markdown("### 2. Shared pipeline configuration")
            with gr.Row():
                ci_in = gr.Dropdown(CI_PLATFORMS, label="CI/CD Platform",
                                    value="github_actions",
                                    elem_id="batch-ci")
                cloud_in = gr.Dropdown(CLOUD_PLATFORMS, label="Cloud Platform",
                                       value="azure",
                                       elem_id="batch-cloud")
            with gr.Row():
                ptype_in = gr.Dropdown(
                    choices=[(lbl, v) for lbl, v in PIPELINE_TYPES],
                    value="all_in_one",
                    label="Pipeline scope",
                    elem_id="batch-ptype",
                )
                iac_in = gr.Dropdown(
                    choices=IAC_TOOLS,
                    value="terraform",
                    label="Infra-as-Code tool",
                    elem_id="batch-iac",
                )

        run_btn = gr.Button("Run batch", variant="primary", elem_id="batch-run")
        status_md = gr.Markdown(
            value=("_Paste your repos, pick the shared config, and hit "
                   "**Run batch**._"),
            elem_id="batch-status",
        )
        gr.Markdown("### 3. Results")
        results_df = gr.DataFrame(
            value=EMPTY_TABLE,
            interactive=False,
            wrap=True,
            elem_id="batch-results",
        )
        # Iteration-26.1: per-repo seconds chart, coloured by outcome
        # (passed / failed_validation / error). Gradio 4.44.1 crashes on
        # BarPlot when it mounts with `color=` set AND no value — we
        # provide the schema-only DataFrame at build time and populate on
        # Run to sidestep that bug.
        chart = gr.BarPlot(
            value=EMPTY_CHART,
            x="repo",
            y="seconds",
            color="outcome",
            title="Per-repo generation time (seconds)",
            tooltip=["repo", "seconds", "outcome"],
            height=320,
            y_title="seconds",
            x_title="repository",
            elem_id="batch-chart",
        )
        with gr.Row():
            csv_btn = gr.Button("⬇ Download CSV", elem_id="batch-csv-btn")
            csv_file = gr.File(label="benchmark.csv",
                               elem_id="batch-csv-file",
                               interactive=False)

        # ---------- wiring ----------
        run_btn.click(
            _run_batch,
            inputs=[repos_in, pat_in, ci_in, cloud_in, ptype_in, iac_in,
                    exp_in, token_state],
            outputs=[status_md, results_df, chart, csv_file],
        )
        csv_btn.click(
            _download_csv,
            inputs=[results_df],
            outputs=[csv_file],
        )
