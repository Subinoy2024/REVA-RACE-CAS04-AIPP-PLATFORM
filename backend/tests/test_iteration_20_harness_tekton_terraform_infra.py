"""Iteration-20 (P1) — Harness + Tekton production-grade Terraform infra flow.

Brings Harness and Tekton generators up to parity with the ADO + GitHub
Actions + GitLab CI 4-stage Terraform flow already covered by
iteration-17/20 tests. Contracts checked here:

  * 4 stages/tasks named validate → plan → policy → apply
  * OPA/conftest gate in the policy stage
  * Manual approval on apply (HarnessApproval for Harness, params.APPROVED
    gate for Tekton)
  * Non-infra pipeline_type still uses the legacy render() path
"""

from __future__ import annotations

import yaml

import pytest

from backend.generators.harness import HarnessGenerator
from backend.generators.tekton import TektonGenerator
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


def _tech() -> TechnologyProfile:
    return TechnologyProfile(
        language="python", framework="fastapi", package_manager="pip",
        build_tool="pip", test_framework="pytest",
        container_ready=True, kubernetes_ready=False, helm_ready=False,
    )


def _plan(cloud: str, ci: str) -> PipelinePlan:
    return PipelinePlan(
        ci_platform=CIPlatform(ci),
        cloud_platform=CloudPlatform(cloud),
        stages=[PipelineStage(
            name="terraform_plan", purpose="provision infra",
            tools=["terraform"], depends_on=[], optional=False, explanation="e",
        )],
        artifacts_strategy="a", security_strategy="s",
        approval_strategy="m", notifications=[],
        custom_requirement_addressed="",
    )


def _env_prod() -> EnvironmentPlan:
    return EnvironmentPlan(rules=[EnvironmentRule(
        name=EnvironmentName("production"), trigger="main_branch",
        requires_approval=True, health_check=True, smoke_test=True,
    )])


# --------------------------------------------------------------------------- #
# Harness — 4-stage Terraform infra pipeline
# --------------------------------------------------------------------------- #
def _harness_render(cloud: str) -> tuple[str, dict]:
    gen = HarnessGenerator(
        plan=_plan(cloud, "harness"), env_plan=_env_prod(),
        tech=_tech(), repo_name="demo", pipeline_type="infra",
    )
    text = gen.render()
    body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    return text, yaml.safe_load(body)


class TestHarnessInfraFourStages:
    @pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
    def test_pipeline_has_four_terraform_stages(self, cloud):
        _, doc = _harness_render(cloud)
        ids = [s["stage"]["identifier"] for s in doc["pipeline"]["stages"]]
        assert ids == [
            "terraform_validate", "terraform_plan",
            "terraform_policy", "terraform_apply",
        ]

    @pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
    def test_all_stages_are_custom_type(self, cloud):
        _, doc = _harness_render(cloud)
        for s in doc["pipeline"]["stages"]:
            assert s["stage"]["type"] == "Custom"

    def test_validate_runs_fmt_init_validate_tflint_tfsec(self):
        _, doc = _harness_render("aws")
        val = doc["pipeline"]["stages"][0]["stage"]
        cmds = " ".join(
            step["step"]["spec"]["command"]
            for step in val["spec"]["execution"]["steps"]
        )
        assert "terraform fmt -check -recursive" in cmds
        assert "terraform init" in cmds
        assert "terraform validate" in cmds
        assert "tflint" in cmds
        assert "tfsec" in cmds

    def test_plan_produces_tfplan_and_plan_json(self):
        # Iteration-20 (P3): swapped to native TerraformPlan step. Instead
        # of a shell command, the plan step now uses Harness's built-in
        # TerraformPlan type with `command: Apply` (i.e. produce a plan to
        # be applied later, not destroy). The plan file lives in Harness's
        # internal state store keyed by provisionerIdentifier.
        _, doc = _harness_render("azure")
        plan_stage = doc["pipeline"]["stages"][1]["stage"]
        steps = plan_stage["spec"]["execution"]["steps"]
        native = [s["step"] for s in steps
                  if s["step"].get("type") == "TerraformPlan"]
        assert native, "expected native TerraformPlan step, got Custom shell"
        assert native[0]["spec"]["configuration"]["command"] == "Apply"
        assert native[0]["spec"]["provisionerIdentifier"] == "aipp_infra"

    def test_policy_uses_conftest_and_optional_terratest(self):
        _, doc = _harness_render("gcp")
        pol = doc["pipeline"]["stages"][2]["stage"]
        cmds = " ".join(
            step["step"]["spec"]["command"]
            for step in pol["spec"]["execution"]["steps"]
        )
        assert "conftest test" in cmds
        assert "go test" in cmds or "Terratest" in cmds

    def test_apply_has_harness_approval_step(self):
        _, doc = _harness_render("aws")
        apply_stage = doc["pipeline"]["stages"][3]["stage"]
        steps = apply_stage["spec"]["execution"]["steps"]
        types = [step["step"]["type"] for step in steps]
        assert "HarnessApproval" in types, (
            "Terraform apply must be guarded by a HarnessApproval step "
            f"(got step types: {types})"
        )

    def test_apply_branch_or_tag_condition(self):
        _, doc = _harness_render("aws")
        apply_stage = doc["pipeline"]["stages"][3]["stage"]
        cond = apply_stage["when"]["condition"]
        # main branch OR v*.*.* tag guard.
        assert "'main'" in cond
        assert "tag" in cond.lower()

    def test_apply_runs_terraform_apply_tfplan(self):
        # Iteration-20 (P3): swapped to native TerraformApply step with
        # `type: InheritFromPlan`. The step reuses the plan produced by
        # the TerraformPlan step in stage 2 (linked by the shared
        # provisionerIdentifier "aipp_infra") — no re-plan, no drift.
        _, doc = _harness_render("aws")
        apply_stage = doc["pipeline"]["stages"][3]["stage"]
        steps = apply_stage["spec"]["execution"]["steps"]
        native = [s["step"] for s in steps
                  if s["step"].get("type") == "TerraformApply"]
        assert native, "expected native TerraformApply step, got Custom shell"
        assert native[0]["spec"]["configuration"]["type"] == "InheritFromPlan"
        assert native[0]["spec"]["provisionerIdentifier"] == "aipp_infra"

    def test_pipeline_variables_include_tf_backend_key(self):
        _, doc = _harness_render("aws")
        names = [v["name"] for v in doc["pipeline"]["variables"]]
        assert "TF_ROOT" in names
        assert "TF_BACKEND_KEY" in names
        assert "TF_APPROVER_GROUP" in names


class TestHarnessNonInfraStillLegacy:
    def test_all_in_one_still_uses_ci_stage(self):
        gen = HarnessGenerator(
            plan=_plan("aws", "harness"), env_plan=_env_prod(),
            tech=_tech(), repo_name="demo", pipeline_type="all_in_one",
        )
        text = gen.render()
        # Legacy pipeline emits a "CI" stage; infra pipeline does not.
        assert "CI:" in text or "identifier: CI" in text
        assert "terraform_apply" not in text


# --------------------------------------------------------------------------- #
# Tekton — 4-task Terraform infra pipeline
# --------------------------------------------------------------------------- #
def _tekton_render(cloud: str) -> tuple[str, list]:
    gen = TektonGenerator(
        plan=_plan(cloud, "tekton"), env_plan=_env_prod(),
        tech=_tech(), repo_name="demo", pipeline_type="infra",
    )
    text = gen.render()
    docs = [d for d in yaml.safe_load_all(text) if d]
    return text, docs


class TestTektonInfraFourTasks:
    @pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
    def test_four_tasks_plus_pipeline(self, cloud):
        _, docs = _tekton_render(cloud)
        kinds = [d["kind"] for d in docs]
        assert kinds.count("Task") == 4
        assert kinds.count("Pipeline") == 1

    @pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
    def test_task_names(self, cloud):
        _, docs = _tekton_render(cloud)
        names = [d["metadata"]["name"] for d in docs if d["kind"] == "Task"]
        assert set(names) == {
            "aipp-tf-validate", "aipp-tf-plan",
            "aipp-tf-policy", "aipp-tf-apply",
        }

    @pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
    def test_pipeline_chains_tasks_in_order(self, cloud):
        _, docs = _tekton_render(cloud)
        pipeline = [d for d in docs if d["kind"] == "Pipeline"][0]
        tasks = pipeline["spec"]["tasks"]
        order = [t["name"] for t in tasks]
        assert order == ["validate", "plan", "policy", "apply"]
        # plan must runAfter validate, policy after plan, apply after policy.
        by = {t["name"]: t for t in tasks}
        assert by["plan"]["runAfter"] == ["validate"]
        assert by["policy"]["runAfter"] == ["plan"]
        assert by["apply"]["runAfter"] == ["policy"]

    def test_all_tasks_share_source_workspace(self):
        _, docs = _tekton_render("aws")
        # Workspace lets tfplan flow validate→plan→policy→apply.
        tasks = [d for d in docs if d["kind"] == "Task"]
        for t in tasks:
            ws = t["spec"]["workspaces"]
            assert any(w["name"] == "source" for w in ws), (
                f"task {t['metadata']['name']} missing 'source' workspace"
            )

    def test_apply_gated_by_approved_param(self):
        _, docs = _tekton_render("aws")
        pipeline = [d for d in docs if d["kind"] == "Pipeline"][0]
        apply_task = [t for t in pipeline["spec"]["tasks"] if t["name"] == "apply"][0]
        when = apply_task["when"]
        approved = [g for g in when if g["input"] == "$(params.APPROVED)"]
        assert approved and "yes" in approved[0]["values"]

    def test_apply_gated_on_main_or_v_tag(self):
        _, docs = _tekton_render("aws")
        pipeline = [d for d in docs if d["kind"] == "Pipeline"][0]
        apply_task = [t for t in pipeline["spec"]["tasks"] if t["name"] == "apply"][0]
        when = apply_task["when"]
        branch_guard = [g for g in when if g["input"] == "$(params.BRANCH)"]
        assert branch_guard
        values = branch_guard[0]["values"]
        assert "main" in values
        assert any(v.startswith("v") for v in values)

    def test_validate_task_runs_tflint_and_tfsec(self):
        _, docs = _tekton_render("gcp")
        val = [d for d in docs if d["kind"] == "Task"
               and d["metadata"]["name"] == "aipp-tf-validate"][0]
        script = val["spec"]["steps"][0]["script"]
        assert "terraform validate" in script
        assert "tflint" in script
        assert "tfsec" in script

    def test_plan_task_produces_tfplan_and_plan_json(self):
        _, docs = _tekton_render("gcp")
        plan = [d for d in docs if d["kind"] == "Task"
                and d["metadata"]["name"] == "aipp-tf-plan"][0]
        script = plan["spec"]["steps"][0]["script"]
        assert "terraform plan -input=false -out=tfplan" in script
        assert "plan.json" in script

    def test_policy_task_runs_conftest_and_terratest(self):
        _, docs = _tekton_render("gcp")
        pol = [d for d in docs if d["kind"] == "Task"
               and d["metadata"]["name"] == "aipp-tf-policy"][0]
        script = pol["spec"]["steps"][0]["script"]
        assert "conftest test" in script
        assert "go test" in script or "Terratest" in script

    def test_apply_task_runs_apply_from_tfplan(self):
        _, docs = _tekton_render("gcp")
        ap = [d for d in docs if d["kind"] == "Task"
              and d["metadata"]["name"] == "aipp-tf-apply"][0]
        script = ap["spec"]["steps"][0]["script"]
        assert "terraform apply -input=false -auto-approve tfplan" in script

    def test_pipeline_declares_tf_root_and_backend_params(self):
        _, docs = _tekton_render("aws")
        pipeline = [d for d in docs if d["kind"] == "Pipeline"][0]
        params = [p["name"] for p in pipeline["spec"]["params"]]
        assert "TF_ROOT" in params
        assert "TF_BACKEND_KEY" in params
        assert "APPROVED" in params


class TestTektonNonInfraStillLegacy:
    def test_all_in_one_still_uses_container_build_push_task(self):
        gen = TektonGenerator(
            plan=_plan("aws", "tekton"), env_plan=_env_prod(),
            tech=_tech(), repo_name="demo", pipeline_type="all_in_one",
        )
        text = gen.render()
        assert "container-build-push" in text
        assert "aipp-tf-apply" not in text


# --------------------------------------------------------------------------- #
# Cross-generator parity — every one of the 5 CIs supports pipeline_type=infra
# --------------------------------------------------------------------------- #
class TestAllFiveCIsSupportInfraFlow:
    """Parity check: for a fixed cloud, all 5 generators produce something
    that contains the words `terraform` + `apply` + `conftest` (the OPA gate),
    proving the 4-stage flow ships in every generator."""

    @pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
    def test_ado_gh_gitlab_harness_tekton_all_emit_terraform_flow(self, cloud):
        from backend.generators.azure_devops import AzureDevOpsGenerator
        from backend.generators.github_actions import GitHubActionsGenerator
        from backend.generators.gitlab_ci import GitLabCIGenerator

        gens = [
            (AzureDevOpsGenerator, "azure_devops"),
            (GitHubActionsGenerator, "github_actions"),
            (GitLabCIGenerator, "gitlab_ci"),
            (HarnessGenerator, "harness"),
            (TektonGenerator, "tekton"),
        ]
        for cls, ci in gens:
            gen = cls(
                plan=_plan(cloud, ci), env_plan=_env_prod(),
                tech=_tech(), repo_name="demo", pipeline_type="infra",
            )
            text = gen.render().lower()
            assert "terraform" in text, f"{ci} missing terraform"
            assert "apply" in text, f"{ci} missing apply stage"
            assert "conftest" in text, f"{ci} missing OPA/conftest gate"
