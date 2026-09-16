"""Directive-trace tests.

These verify the new machine-checkable audit trail that proves a user's
`Custom deployment requirement` was (a) recognised by the parser and
(b) enforced in the emitted YAML.

Coverage:
  1. Empty directive     → status=no_directive_provided, evidence all False/0.
  2. Recognised + Python → status=recognised_and_enforced, matched_pattern set,
                           az_cli count = 0, python_sdk count > 0, banner True.
  3. Non-matching text   → status=not_recognised, matched_pattern is None.
  4. Commit-scoped tag   → detects $(Build.SourceVersion), github.sha, CI_COMMIT_SHA.
"""

from __future__ import annotations

from backend.generators.azure_devops import AzureDevOpsGenerator
from backend.generators.base import build_directive_trace, parse_deploy_style
from backend.models.environment import (
    EnvironmentName,
    EnvironmentPlan,
    EnvironmentRule,
)
from backend.models.pipeline import (
    CIPlatform,
    CloudPlatform,
    PipelinePlan,
    TechnologyProfile,
)


def _mk_ado_yaml(*, custom_requirement: str) -> str:
    """Render a full Azure DevOps YAML for trace inspection."""
    plan = PipelinePlan(
        ci_platform=CIPlatform.azure_devops,
        cloud_platform=CloudPlatform.azure,
        stages=[],
        artifacts_strategy="acr",
        security_strategy="trivy",
        approval_strategy="manual",
        notifications=[],
        custom_requirement_addressed="",
    )
    env = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch"),
        EnvironmentRule(
            name=EnvironmentName.production, trigger="version_tag",
            requires_approval=True,
        ),
    ])
    tech = TechnologyProfile(
        language="python", framework="fastapi", package_manager="pip",
        containerized=True, kubernetes_ready=False,
        test_frameworks=["pytest"], build_tools=[], notes=[],
    )
    return AzureDevOpsGenerator(
        plan=plan, env_plan=env, tech=tech, repo_name="demo",
        pipeline_type="all_in_one",
        custom_requirement=custom_requirement,
    ).render()


# ---------------------------------------------------------------------------
# 1. Empty directive
# ---------------------------------------------------------------------------
def test_empty_directive_returns_no_directive_provided():
    yaml_text = _mk_ado_yaml(custom_requirement="")
    trace = build_directive_trace(custom_requirement="", yaml_text=yaml_text)
    assert trace["enforcement_status"] == "no_directive_provided"
    assert trace["recognised"] is False
    assert trace["matched_pattern"] is None
    assert trace["deploy_style"] == "cli"
    assert trace["yaml_evidence"]["banner_present"] is False


# ---------------------------------------------------------------------------
# 2. Recognised + Python-SDK enforcement
# ---------------------------------------------------------------------------
def test_python_directive_recognised_and_enforced():
    directive = (
        "i need image version should be change each and every commit , "
        "in that repo we should use python scripting to complete the "
        "pipeline .no other scripting language . create industry level pipeline"
    )
    yaml_text = _mk_ado_yaml(custom_requirement=directive)
    trace = build_directive_trace(custom_requirement=directive, yaml_text=yaml_text)

    assert trace["recognised"] is True
    assert trace["matched_pattern"] is not None
    assert trace["deploy_style"] == "python"
    assert trace["enforcement_status"] == "recognised_and_enforced"

    ev = trace["yaml_evidence"]
    assert ev["banner_present"] is True
    assert ev["az_cli_in_deploy_stage_count"] == 0, (
        "python-style deploy MUST NOT emit AzureCLI@2 tasks inside a "
        "deploy_* stage — found "
        f"{ev['az_cli_in_deploy_stage_count']} in YAML"
    )
    # A package-stage AzureCLI@2 for ACR login is legitimate — so the
    # total may be >= 0; we don't constrain it here.
    assert ev["python_sdk_task_count"] > 0
    assert ev["commit_scoped_image"] is True
    assert "Build.SourceVersion" in (ev["image_tag_expression"] or "")


# ---------------------------------------------------------------------------
# 3. Non-matching text
# ---------------------------------------------------------------------------
def test_random_text_is_not_recognised():
    directive = "please make the pipeline fast and add coffee to the runners"
    yaml_text = _mk_ado_yaml(custom_requirement=directive)
    trace = build_directive_trace(custom_requirement=directive, yaml_text=yaml_text)
    assert trace["enforcement_status"] == "not_recognised"
    assert trace["matched_pattern"] is None
    assert trace["deploy_style"] == "cli"
    # The banner still fires because we always echo the user's raw text.
    assert trace["yaml_evidence"]["banner_present"] is True


# ---------------------------------------------------------------------------
# 4. parse_deploy_style backward compat
# ---------------------------------------------------------------------------
def test_parse_deploy_style_backcompat():
    assert parse_deploy_style(None) == "cli"
    assert parse_deploy_style("") == "cli"
    assert parse_deploy_style("hello") == "cli"
    assert parse_deploy_style("please use python") == "python"
    assert parse_deploy_style("NO AZ CLI, please") == "python"


# ---------------------------------------------------------------------------
# 5. GitHub Actions / GitLab tag expressions are recognised as commit-scoped
# ---------------------------------------------------------------------------
def test_github_sha_tag_expression_detected():
    yaml_text = "vars:\n  TAG: ${{ github.sha }}\nsteps: []\n"
    trace = build_directive_trace(custom_requirement="", yaml_text=yaml_text)
    assert trace["yaml_evidence"]["commit_scoped_image"] is True
    assert "github.sha" in trace["yaml_evidence"]["image_tag_expression"]


def test_gitlab_sha_tag_expression_detected():
    yaml_text = "variables:\n  TAG: $CI_COMMIT_SHA\n"
    trace = build_directive_trace(custom_requirement="", yaml_text=yaml_text)
    assert trace["yaml_evidence"]["commit_scoped_image"] is True


# ---------------------------------------------------------------------------
# 6. Single-stage ("without multistage") directive recognised and enforced
# ---------------------------------------------------------------------------
def test_without_multistage_directive_enforced():
    directive = "I want without multistage pipeline"
    yaml_text = _mk_ado_yaml(custom_requirement=directive)
    trace = build_directive_trace(
        custom_requirement=directive,
        yaml_text=yaml_text,
        llm_acknowledgement="Custom requirement addressed: pipeline will be implemented without a multistage setup.",
    )
    assert trace["enforcement_status"] == "recognised_and_enforced"
    assert trace["recognised"] is True
    assert trace["is_single_stage"] is True
    assert "stages:" not in yaml_text
    assert "jobs:" in yaml_text


# ---------------------------------------------------------------------------
# 7. General custom requirement handled by AI planner
# ---------------------------------------------------------------------------
def test_general_prompt_handled_by_planner():
    directive = "deploy to dev namespace with helm and notify slack on failure"
    yaml_text = _mk_ado_yaml(custom_requirement=directive)
    trace = build_directive_trace(
        custom_requirement=directive,
        yaml_text=yaml_text,
        llm_acknowledgement="Custom requirement addressed: slack notifications added to pipeline.",
    )
    assert trace["enforcement_status"] == "handled_by_planner"
    assert trace["recognised"] is True

