"""Common helpers for CI/CD generators."""

from __future__ import annotations

import logging
import re
from typing import Iterable

from backend.models.environment import EnvironmentPlan
from backend.models.pipeline import PipelinePlan, TechnologyProfile

logger = logging.getLogger("aipp.directive")


# ---------------------------------------------------------------------------
# Iteration-26.3 · Custom-requirement directive parser
# ---------------------------------------------------------------------------
# The user can add free-form guidance in the `Custom deployment requirement`
# textarea. We honour a small, deterministic set of directives that reshape
# the emitted YAML — without asking the LLM to invent them.
#
# Currently supported directives (case-insensitive substring match):
#
#   "no az cli", "no azure cli", "avoid az cli", "without az cli",
#   "python only", "python script", "use python"
#     -> switches Azure DevOps / GitHub Actions / GitLab CI deploy steps
#        from CLI-based (az / aws / gcloud) to a Python-SDK based Python
#        task. The user's exact wording is echoed back in a comment above
#        the deploy stage so they can verify the intent was honoured.
# ---------------------------------------------------------------------------
_NO_CLI_PATTERNS = [
    r"no\s+az\s*cli",
    r"no\s+azure\s*cli",
    r"avoid\s+az\s*cli",
    r"without\s+az\s*cli",
    r"don'?t\s+use\s+az\s*cli",
    r"don'?t\s+use\s+azure\s*cli",
    r"python\s+only",
    r"python\s+script",
    r"use\s+python",
    r"only\s+python",
]


_SINGLE_STAGE_PATTERNS = [
    r"without\s+(a\s+)?multi[- ]?stage",
    r"without\s+multistage",
    r"no\s+multi[- ]?stage",
    r"no\s+multistage",
    r"single\s+stage",
    r"single\s+job",
    r"flat\s+pipeline",
    r"one\s+stage",
    r"disable\s+multi[- ]?stage",
]


def is_single_stage(custom_requirement: str | None) -> tuple[bool, str | None]:
    """Return `(is_single_stage_requested, matched_pattern)`."""
    if not custom_requirement:
        return False, None
    text = custom_requirement.lower()
    for pat in _SINGLE_STAGE_PATTERNS:
        if re.search(pat, text):
            return True, pat
    return False, None


def _match_directive(custom_requirement: str | None) -> tuple[str, str | None]:
    """Return `(deploy_style, matched_pattern_or_None)`.

    Kept private and used by both `parse_deploy_style` (back-compat, returns
    only the style) and `build_directive_trace` (needs the pattern too).
    """
    if not custom_requirement:
        return "cli", None
    text = custom_requirement.lower()
    for pat in _NO_CLI_PATTERNS:
        if re.search(pat, text):
            return "python", pat
    return "cli", None


def parse_deploy_style(custom_requirement: str | None) -> str:
    """Return `"python"` if the user forbade CLI-based deploys, else `"cli"`.

    Emits an INFO-level log line so operators can grep
    `docker compose logs backend | grep aipp.directive` and see, for every
    generation, exactly which regex matched (or that the input was ignored).
    """
    style, matched = _match_directive(custom_requirement)
    if custom_requirement:
        snippet = (custom_requirement or "").strip().replace("\n", " ")[:120]
        if matched:
            logger.info(
                "directive.parsed style=%s matched=%r input=%r",
                style, matched, snippet,
            )
        else:
            logger.info(
                "directive.parsed style=%s matched=None input=%r "
                "(no CLI-avoidance keyword found — deploy uses standard CLI tasks)",
                style, snippet,
            )
    return style


def build_directive_trace(
    *,
    custom_requirement: str | None,
    yaml_text: str,
    llm_acknowledgement: str | None = None,
) -> dict:
    """Produce a machine-checkable audit trail proving the directive was
    (a) recognised by the parser and (b) enforced in the emitted YAML.

    Returned shape (stable, safe to render in the UI or persist):
        {
          "directive_text":       "<verbatim user input>",
          "recognised":           True/False,
          "matched_pattern":      "<regex>" | None,
          "deploy_style":         "cli" | "python",
          "is_single_stage":      True/False,
          "llm_acknowledgement":  "<planner's custom_requirement_addressed>",
          "yaml_evidence": {
              "banner_present":         True/False,
              "az_cli_task_count":      <int>,
              "python_sdk_task_count":  <int>,
              "image_tag_expression":   "<TAG: … from vars block>" | None,
              "commit_scoped_image":    True/False,
              "is_single_stage":        True/False | None,
          },
          "enforcement_status":  "recognised_and_enforced"
                               | "recognised_but_no_yaml_change"
                               | "handled_by_planner"
                               | "not_recognised",
        }
    """
    style, matched = _match_directive(custom_requirement)
    single_req, single_pat = is_single_stage(custom_requirement)
    text = (custom_requirement or "").strip()

    # ---- YAML self-inspection ------------------------------------------
    banner_present = "CUSTOM DEPLOYMENT REQUIREMENT (as entered by the user)" in yaml_text
    is_single_stage_yaml = (
        "stages:" not in yaml_text
        or yaml_text.count("- stage:") <= 1
    )

    # Total AzureCLI@2 tasks anywhere in the YAML. Note: a task may
    # legitimately remain in the *package* stage for ACR login even when
    # the *deploy* stage was switched to Python. We therefore expose both
    # a total and a deploy-stage-only count.
    az_cli_total = yaml_text.count("AzureCLI@2")

    # Slice the YAML from the first deploy-stage marker onwards to count
    # AzureCLI@2 usage specifically inside deploy stages. Works for the
    # Azure DevOps generator's `- stage: deploy_dev` / `deploy_prod` shape.
    deploy_slice = ""
    for marker in ("- stage: deploy_dev", "- stage: deploy_prod",
                   "- stage: deploy_production", "- stage: deploy_staging",
                   "- stage: deploy"):
        idx = yaml_text.find(marker)
        if idx >= 0:
            deploy_slice = yaml_text[idx:]
            break
    az_cli_deploy = deploy_slice.count("AzureCLI@2")

    python_sdk_count = (
        yaml_text.count("UsePythonVersion@0")
        + yaml_text.count("azure-identity")
        + yaml_text.count("azure-mgmt-web")
        + yaml_text.count("azure-mgmt-containerservice")
    )
    # Extract the TAG expression (commit-scoped image detection).
    tag_match = re.search(r"^\s*TAG:\s*(.+?)\s*$", yaml_text, re.MULTILINE)
    image_tag_expr = tag_match.group(1).strip() if tag_match else None
    commit_scoped = bool(
        image_tag_expr and (
            "Build.SourceVersion" in image_tag_expr    # Azure DevOps
            or "github.sha" in image_tag_expr           # GitHub Actions
            or "CI_COMMIT_SHA" in image_tag_expr        # GitLab CI
            or "commit" in image_tag_expr.lower()
        )
    )

    # ---- Enforcement verdict -------------------------------------------
    if not text:
        status = "no_directive_provided"
    elif single_req and is_single_stage_yaml:
        status = "recognised_and_enforced"
        matched = single_pat
    elif single_req:
        status = "recognised_but_no_yaml_change"
        matched = single_pat
    elif matched and style == "python" and python_sdk_count > 0 and az_cli_deploy == 0:
        status = "recognised_and_enforced"
    elif matched and style == "python":
        status = "recognised_but_no_yaml_change"
    elif matched:
        status = "recognised_and_enforced"
    elif (llm_acknowledgement or "").strip():
        status = "handled_by_planner"
    else:
        status = "not_recognised"

    return {
        "directive_text": text,
        "recognised": (matched is not None or status == "handled_by_planner"),
        "matched_pattern": matched,
        "deploy_style": style,
        "is_single_stage": is_single_stage_yaml if single_req else False,
        "llm_acknowledgement": (llm_acknowledgement or "").strip() or None,
        "yaml_evidence": {
            "banner_present": banner_present,
            "az_cli_task_count": az_cli_total,
            "az_cli_in_deploy_stage_count": az_cli_deploy,
            "python_sdk_task_count": python_sdk_count,
            "image_tag_expression": image_tag_expr,
            "commit_scoped_image": commit_scoped,
            "is_single_stage": is_single_stage_yaml if single_req else None,
        },
        "enforcement_status": status,
    }


class BaseGenerator:
    filename: str = "pipeline.yml"

    def __init__(
        self,
        *,
        plan: PipelinePlan,
        env_plan: EnvironmentPlan,
        tech: TechnologyProfile,
        repo_name: str,
        pipeline_type: str = "all_in_one",
        agent_pool: str | None = None,
        custom_requirement: str | None = None,
    ) -> None:
        self.plan = plan
        self.env_plan = env_plan
        self.tech = tech
        self.repo_name = repo_name
        self.pipeline_type = pipeline_type or "all_in_one"
        # `None` means Microsoft-hosted `vmImage: ubuntu-22.04` (default).
        # Any string is treated as a self-hosted agent pool name.
        self.agent_pool = (agent_pool or "").strip() or None
        # Free-form user directive (kept for downstream comment injection).
        self.custom_requirement = (custom_requirement or "").strip()
        # Parsed style: `"cli"` (default) or `"python"` (user opted out of CLI).
        self.deploy_style = parse_deploy_style(self.custom_requirement)
        self.is_single_stage, self.single_stage_pattern = is_single_stage(self.custom_requirement)

    # -----------------------------------------------------------------
    # Runner / agent selection helpers — used by every CI generator.
    # Each generator's YAML syntax for "which agent runs this job?" is
    # different, so we expose the same logical knob under three names.
    # -----------------------------------------------------------------
    def _gh_runs_on(self) -> object:
        """GitHub Actions `runs-on:` value.

        - No pool → `ubuntu-22.04` (GitHub-hosted default).
        - Any pool → `[self-hosted, <pool-label>]` — the job runs only on
          a self-hosted runner that has both labels.
        """
        if not self.agent_pool:
            return "ubuntu-22.04"
        return ["self-hosted", self.agent_pool]

    def _gitlab_tags(self) -> list | None:
        """GitLab CI job `tags:` value.

        - No pool → `None` (job runs on shared runners).
        - Any pool → `[<pool>]` — matched against the runner's tags.
        """
        if not self.agent_pool:
            return None
        return [self.agent_pool]

    def render(self) -> str:  # noqa: D401
        raise NotImplementedError

    # ---------- shared helpers ----------
    def language_setup_snippet(self) -> list[str]:
        lang = (self.tech.language or "").lower()
        if lang == "python":
            return ["Setup Python", "Install deps: pip install -r requirements.txt"]
        if lang in {"javascript", "typescript"}:
            pm = self.tech.package_manager or "npm"
            return [f"Setup Node.js", f"Install deps: {pm} install"]
        if lang == "java":
            return ["Setup JDK 17", "Build: mvn -B verify"]
        if lang == "go":
            return ["Setup Go", "Build: go build ./..."]
        return ["Setup toolchain", "Install dependencies"]

    def image_name(self, env: str = "app") -> str:
        # generic image reference; the real registry differs per cloud
        return f"registry.example.com/{self.repo_name}:${{{{ github.sha }}}}"

    def stage_names(self) -> list[str]:
        return [s.name for s in self.plan.stages]


# ---------------------------------------------------------------------------
# Post-processing helper — inject `#` comments into a yaml.safe_dump string.
# ---------------------------------------------------------------------------
def inject_comments(yaml_text: str, comments: dict[str, list[str]]) -> str:
    """Inject `#`-prefixed comment blocks *above* matching lines.

    Args:
        yaml_text: output of `yaml.safe_dump(...)`.
        comments:  mapping of exact substring → list of comment lines to
                   insert on the lines immediately BEFORE the first line
                   containing that substring. Indentation is inferred
                   from the target line.

    Design: PyYAML drops comments, and generator dicts are dense/large.
    Manually string-editing after safe_dump keeps our generators tiny
    while still producing human-readable, commented YAML.
    """
    if not comments:
        return yaml_text
    lines = yaml_text.splitlines()
    out: list[str] = []
    matched: set[str] = set()
    for line in lines:
        for marker, comment_lines in comments.items():
            if marker in matched or marker not in line:
                continue
            indent = " " * (len(line) - len(line.lstrip(" ")))
            for cl in comment_lines:
                out.append(f"{indent}# {cl}" if cl else f"{indent}#")
            matched.add(marker)
        out.append(line)
    return "\n".join(out) + ("\n" if yaml_text.endswith("\n") else "")


# ---------------------------------------------------------------------------
# Reusable comment map for common CI stages / jobs (non-infra path).
# Every generator can plug this into inject_comments() so *all* pipelines
# — not just Terraform infra — get human-readable inline docs.
# ---------------------------------------------------------------------------
COMMON_STAGE_COMMENTS: dict[str, list[str]] = {
    # ADO uses `- stage: build`; GH/GitLab use `build:`; both are matched
    # by substring on the exact same key.
    "stage: build": [
        "-----------------------------------------------------------",
        "STAGE · BUILD — checkout + language runtime + install + build",
        "+ unit tests + publish artefact.",
        "-----------------------------------------------------------",
    ],
    "stage: security": [
        "-----------------------------------------------------------",
        "STAGE · SECURITY — SAST (Snyk / Semgrep) + dependency-audit +",
        "lint. Findings surface as build-log warnings so devs act early.",
        "-----------------------------------------------------------",
    ],
    "stage: package": [
        "-----------------------------------------------------------",
        "STAGE · PACKAGE — container build (multi-arch) + Trivy image",
        "scan + push to registry (ACR / ECR / GCR / Docker Hub).",
        "-----------------------------------------------------------",
    ],
    "stage: deploy_dev": [
        "-----------------------------------------------------------",
        "STAGE · DEPLOY (dev) — auto on every main-branch push.",
        "Smoke-test hooks after deploy verify the app came up healthy.",
        "-----------------------------------------------------------",
    ],
    "stage: deploy_staging": [
        "-----------------------------------------------------------",
        "STAGE · DEPLOY (staging) — auto on main; runs smoke tests.",
        "-----------------------------------------------------------",
    ],
    "stage: deploy_prod": [
        "-----------------------------------------------------------",
        "STAGE · DEPLOY (prod) — requires manual approval on the ADO",
        "Environments tab (or GH environment). Version-tag guarded.",
        "-----------------------------------------------------------",
    ],
    "stage: deploy_production": [
        "-----------------------------------------------------------",
        "STAGE · DEPLOY (production) — manual approval + version-tag gate.",
        "-----------------------------------------------------------",
    ],
    # GH Actions / GitLab job shape (top-level key, ends with colon).
    "  build:": [
        "-----------------------------------------------------------",
        "JOB · BUILD — checkout + install + unit tests + upload artefact.",
        "-----------------------------------------------------------",
    ],
    "  security:": [
        "-----------------------------------------------------------",
        "JOB · SECURITY — SAST + dependency-audit + lint (soft-fail).",
        "-----------------------------------------------------------",
    ],
    "  package:": [
        "-----------------------------------------------------------",
        "JOB · PACKAGE — docker build + Trivy scan + push to registry.",
        "-----------------------------------------------------------",
    ],
    "  deploy_dev:": [
        "-----------------------------------------------------------",
        "JOB · DEPLOY (dev) — main-branch push triggers auto-deploy.",
        "-----------------------------------------------------------",
    ],
    "  deploy_prod:": [
        "-----------------------------------------------------------",
        "JOB · DEPLOY (prod) — version-tag guarded + manual approval.",
        "-----------------------------------------------------------",
    ],
}


def default_pipeline_header(
    *,
    ci: str,
    cloud: str,
    scope: str,
    custom_requirement: str | None = None,
    deploy_style: str | None = None,
) -> str:
    """Compact header comment for a non-infra pipeline. Keep it short —
    a user opening the file at line 1 should know what they're looking at.

    If `custom_requirement` is non-empty, an extra block echoes back the
    user's directive verbatim and reports how AIPP interpreted it
    (`deploy_style` = "cli" or "python"). This is the ONLY visible proof
    a user has, at the top of the YAML, that their free-form request was
    read and acted upon.
    """
    base = (
        "# ==================================================================\n"
        f"#  AIPP-generated {ci} pipeline · target cloud: {cloud} · scope: {scope}\n"
        "#  Standard flow: build → security → package (→ deploy_dev → deploy_prod).\n"
        "#  Every stage gets a short `#` header comment so the file reads\n"
        "#  top-to-bottom like a checklist. Modify freely — YAML only, no hidden magic.\n"
        "# ==================================================================\n"
    )
    req = (custom_requirement or "").strip()
    if not req:
        return base

    # Wrap the user's text at ~72 chars so long directives stay readable.
    wrapped: list[str] = []
    for paragraph in req.splitlines() or [req]:
        paragraph = paragraph.strip()
        if not paragraph:
            wrapped.append("")
            continue
        line = ""
        for word in paragraph.split():
            if len(line) + len(word) + 1 > 72:
                wrapped.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        if line:
            wrapped.append(line)

    style = (deploy_style or "cli").lower()
    if style == "python":
        interp = (
            "AIPP directive parser: deploy stages switched to the Python "
            "SDK path (no `az` / `aws` / `gcloud` CLI in deploy steps)."
        )
    else:
        interp = (
            "AIPP directive parser: no CLI-avoidance keywords detected — "
            "deploy stages use the standard cloud CLI tasks."
        )
    # Wrap interpretation line too.
    interp_lines: list[str] = []
    line = ""
    for word in interp.split():
        if len(line) + len(word) + 1 > 72:
            interp_lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        interp_lines.append(line)

    banner = (
        "#\n"
        "# ------------------------------------------------------------------\n"
        "#  CUSTOM DEPLOYMENT REQUIREMENT (as entered by the user)\n"
        "# ------------------------------------------------------------------\n"
    )
    for wl in wrapped:
        banner += f"#  > {wl}\n" if wl else "#\n"
    banner += "#\n"
    for il in interp_lines:
        banner += f"#  {il}\n"
    banner += "# ==================================================================\n"
    return base + banner
