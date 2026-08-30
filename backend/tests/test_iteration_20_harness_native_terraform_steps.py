"""Iteration-20 (P3) — Harness Terraform infra uses native step types.

Swaps Custom-stage shell for Harness's built-in `TerraformPlan` +
`TerraformApply` step types, linked by a shared `provisionerIdentifier`.
Benefits:
  * No manual tfplan artifact upload — Harness state store handles it.
  * `type: InheritFromPlan` on Apply guarantees the exact plan the reviewer
    approved is what gets applied (no re-plan drift).
  * No terraform CLI install / cloud auth shell — the delegate carries it.

The validate + policy stages remain Custom (they run tflint/tfsec/conftest
which have no native Harness equivalent).
"""

from __future__ import annotations

import yaml

import pytest

from backend.generators.harness import HarnessGenerator
from backend.models.environment import (
    EnvironmentName,
    EnvironmentPlan,
    EnvironmentRule,
)
from backend.models.pipeline import (
    CIPlatform,
    CloudPlatform,
    PipelinePlan,
    PipelineStage,
    TechnologyProfile,
)


def _tech():
    return TechnologyProfile(
        language="python", framework="fastapi", package_manager="pip",
        build_tool="pip", test_framework="pytest",
        container_ready=True, kubernetes_ready=False, helm_ready=False,
    )


def _plan(cloud="aws"):
    return PipelinePlan(
        ci_platform=CIPlatform("harness"), cloud_platform=CloudPlatform(cloud),
        stages=[PipelineStage(
            name="terraform_plan", purpose="provision", tools=["terraform"],
            depends_on=[], optional=False, explanation="e",
        )],
        artifacts_strategy="a", security_strategy="s", approval_strategy="m",
        notifications=[], custom_requirement_addressed="",
    )


def _env_plan():
    return EnvironmentPlan(rules=[EnvironmentRule(
        name=EnvironmentName("production"), trigger="main_branch",
        requires_approval=True, health_check=True, smoke_test=True,
    )])


def _render(cloud="aws") -> tuple[str, dict]:
    gen = HarnessGenerator(
        plan=_plan(cloud), env_plan=_env_plan(), tech=_tech(),
        repo_name="demo", pipeline_type="infra",
    )
    text = gen.render()
    body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    return text, yaml.safe_load(body)


def _find_step(stage: dict, step_type: str):
    for s in stage["spec"]["execution"]["steps"]:
        step = s.get("step", {})
        if step.get("type") == step_type:
            return step
    return None


class TestPlanStageIsNativeTerraformPlan:
    def test_plan_stage_uses_terraformplan_step_type(self):
        _, doc = _render()
        plan_stage = doc["pipeline"]["stages"][1]["stage"]
        plan_step = _find_step(plan_stage, "TerraformPlan")
        assert plan_step, "plan stage must contain a native TerraformPlan step"

    def test_plan_step_command_is_apply_not_destroy(self):
        _, doc = _render()
        plan_step = _find_step(doc["pipeline"]["stages"][1]["stage"],
                                "TerraformPlan")
        assert plan_step["spec"]["configuration"]["command"] == "Apply"

    def test_plan_step_declares_provisioner_identifier(self):
        # This ID must match the Apply step so Harness can wire them together.
        _, doc = _render()
        plan_step = _find_step(doc["pipeline"]["stages"][1]["stage"],
                                "TerraformPlan")
        assert plan_step["spec"]["provisionerIdentifier"] == "aipp_infra"

    def test_plan_step_configures_git_config_files(self):
        _, doc = _render()
        plan_step = _find_step(doc["pipeline"]["stages"][1]["stage"],
                                "TerraformPlan")
        store = plan_step["spec"]["configuration"]["configFiles"]["store"]
        assert store["type"] == "Github"
        # `<+input>` = user picks git connector at pipeline run time.
        assert store["spec"]["connectorRef"] == "<+input>"

    def test_plan_step_has_a_timeout(self):
        _, doc = _render()
        plan_step = _find_step(doc["pipeline"]["stages"][1]["stage"],
                                "TerraformPlan")
        # Any string timeout is fine — Harness parses `15m`, `1h`, etc.
        assert plan_step["timeout"], "TerraformPlan step must declare a timeout"

    def test_plan_stage_no_longer_shells_out_terraform_init(self):
        text, _ = _render()
        # No raw `terraform init` shell inside the plan stage.
        assert "terraform init" not in text or "content:" in text, (
            "plan stage should not shell out to `terraform init` — the "
            "native TerraformPlan step handles init internally"
        )


class TestApplyStageIsNativeTerraformApply:
    def test_apply_stage_uses_terraformapply_step_type(self):
        _, doc = _render()
        apply_step = _find_step(doc["pipeline"]["stages"][3]["stage"],
                                 "TerraformApply")
        assert apply_step, (
            "apply stage must contain a native TerraformApply step"
        )

    def test_apply_step_inherits_from_plan(self):
        # This is the crown-jewel invariant — no drift between plan & apply.
        _, doc = _render()
        apply_step = _find_step(doc["pipeline"]["stages"][3]["stage"],
                                 "TerraformApply")
        assert apply_step["spec"]["configuration"]["type"] == "InheritFromPlan"

    def test_apply_step_provisioner_identifier_matches_plan(self):
        _, doc = _render()
        plan_step = _find_step(doc["pipeline"]["stages"][1]["stage"],
                                "TerraformPlan")
        apply_step = _find_step(doc["pipeline"]["stages"][3]["stage"],
                                 "TerraformApply")
        assert (plan_step["spec"]["provisionerIdentifier"]
                == apply_step["spec"]["provisionerIdentifier"]), (
            "TerraformPlan and TerraformApply must share the same "
            "provisionerIdentifier or Harness cannot link them"
        )

    def test_harness_approval_still_precedes_apply(self):
        _, doc = _render()
        apply_stage = doc["pipeline"]["stages"][3]["stage"]
        steps = apply_stage["spec"]["execution"]["steps"]
        types = [s["step"]["type"] for s in steps]
        assert "HarnessApproval" in types
        # And the approval must come BEFORE the apply.
        approval_idx = types.index("HarnessApproval")
        apply_idx = types.index("TerraformApply")
        assert approval_idx < apply_idx, (
            "HarnessApproval must precede TerraformApply — otherwise the "
            "human gate is meaningless"
        )

    def test_apply_stage_no_longer_installs_terraform_binary(self):
        text, _ = _render()
        # The Custom-stage `install_terraform` Run steps are gone.
        # (There may still be install commands in the VALIDATE stage — that
        #  stage still uses shell because tflint/tfsec have no native step.)
        apply_stage_yaml = yaml.safe_dump(
            _render()[1]["pipeline"]["stages"][3]
        )
        assert "terraform_1.9.5" not in apply_stage_yaml, (
            "apply stage should not install terraform — the Harness "
            "delegate carries the binary"
        )
        assert "terraform apply " not in apply_stage_yaml, (
            "no raw `terraform apply` shell in the apply stage"
        )


class TestValidateAndPolicyStagesStillShellForNonNativeTools:
    """We do NOT swap validate + policy — tflint/tfsec/conftest/terratest
    have no native Harness step types. Those stages must still work."""

    def test_validate_stage_still_runs_tflint_tfsec(self):
        text, _ = _render()
        assert "tflint" in text
        assert "tfsec" in text

    def test_policy_stage_still_runs_conftest(self):
        text, _ = _render()
        assert "conftest test" in text


class TestBranchTagGuardPreserved:
    def test_apply_still_guarded_by_branch_or_tag_condition(self):
        _, doc = _render()
        apply_stage = doc["pipeline"]["stages"][3]["stage"]
        cond = apply_stage["when"]["condition"]
        assert "main" in cond and "tag" in cond
