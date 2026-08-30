"""Iteration-20 (P1) — GitLab CI production-grade Terraform infra flow.

Extends the 4-stage Terraform pipeline (validate → plan → policy → apply)
that ADO + GitHub Actions already emit to GitLab CI. The rules verified
here mirror the ADO/GH regression tests so cross-generator parity is
enforced by tests, not just code review.
"""

from __future__ import annotations

import yaml

import pytest

from backend.generators.gitlab_ci import GitLabCIGenerator
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


def _plan(cloud: str) -> PipelinePlan:
    return PipelinePlan(
        ci_platform=CIPlatform("gitlab_ci"),
        cloud_platform=CloudPlatform(cloud),
        stages=[PipelineStage(
            name="terraform_plan", purpose="provision infra",
            tools=["terraform"], depends_on=[], optional=False,
            explanation="e",
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


def _render(cloud: str, *, agent_pool: str | None = None) -> tuple[str, dict]:
    gen = GitLabCIGenerator(
        plan=_plan(cloud), env_plan=_env_prod(),
        tech=_tech(), repo_name="demo",
        pipeline_type="infra", agent_pool=agent_pool,
    )
    text = gen.render()
    # Strip leading `#`-header lines for YAML parsing.
    yaml_body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    return text, yaml.safe_load(yaml_body)


class TestFourStageFlow:
    @pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
    def test_stages_are_validate_plan_policy_apply(self, cloud):
        _, doc = _render(cloud)
        assert doc["stages"] == ["validate", "plan", "policy", "apply"]

    @pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
    def test_all_four_jobs_present(self, cloud):
        _, doc = _render(cloud)
        for job in ("terraform_validate", "terraform_plan",
                    "terraform_policy", "terraform_apply"):
            assert job in doc, f"missing {job} in GitLab pipeline"

    @pytest.mark.parametrize("cloud", ["aws", "azure", "gcp"])
    def test_stage_binding(self, cloud):
        _, doc = _render(cloud)
        assert doc["terraform_validate"]["stage"] == "validate"
        assert doc["terraform_plan"]["stage"] == "plan"
        assert doc["terraform_policy"]["stage"] == "policy"
        assert doc["terraform_apply"]["stage"] == "apply"


class TestValidateJob:
    def test_runs_fmt_init_validate_tflint_tfsec(self):
        _, doc = _render("aws")
        script = "\n".join(doc["terraform_validate"]["script"])
        assert "terraform fmt -check -recursive" in script
        assert "terraform init" in script
        assert "terraform validate" in script
        assert "tflint" in script
        assert "tfsec" in script

    def test_backend_key_wired_in_init(self):
        _, doc = _render("aws")
        assert "-backend-config=key=" in "\n".join(
            doc["terraform_validate"]["script"])


class TestPlanJobArtifact:
    def test_plan_uploads_tfplan_and_plan_json_artifact(self):
        _, doc = _render("azure")
        plan = doc["terraform_plan"]
        art_paths = plan["artifacts"]["paths"]
        # Must publish tfplan + plan.json (machine-readable for OPA).
        assert any("tfplan" in p for p in art_paths)
        assert any("plan.json" in p for p in art_paths)

    def test_plan_depends_on_validate(self):
        _, doc = _render("azure")
        needs = doc["terraform_plan"]["needs"]
        # `needs` items may be strings (job names) or dicts.
        needs_names = [n if isinstance(n, str) else n.get("job") for n in needs]
        assert "terraform_validate" in needs_names


class TestPolicyJobSoftFail:
    def test_policy_runs_conftest_against_plan_json(self):
        _, doc = _render("gcp")
        script = "\n".join(doc["terraform_policy"]["script"])
        assert "conftest test" in script
        assert "plan.json" in script

    def test_policy_optionally_runs_terratest(self):
        _, doc = _render("gcp")
        script = "\n".join(doc["terraform_policy"]["script"])
        assert "Terratest" in script or "go test" in script

    def test_policy_is_allow_failure_true(self):
        # OPA + Terratest are advisory in this iteration — they must never
        # block the apply stage on their own.
        _, doc = _render("gcp")
        assert doc["terraform_policy"]["allow_failure"] is True

    def test_policy_needs_plan_artifacts(self):
        _, doc = _render("gcp")
        needs = doc["terraform_policy"]["needs"]
        # Must download the tfplan artifact — so `artifacts: True` on the
        # plan-job dependency.
        entries = [n for n in needs if isinstance(n, dict)]
        assert any(n.get("job") == "terraform_plan" and n.get("artifacts") is True
                   for n in entries), needs


class TestApplyGate:
    def test_apply_is_manual(self):
        _, doc = _render("aws")
        assert doc["terraform_apply"]["when"] == "manual"

    def test_apply_only_on_main_or_v_tag(self):
        _, doc = _render("aws")
        rules = doc["terraform_apply"]["rules"]
        rule_text = " ".join(str(r) for r in rules)
        # main branch OR v*.*.* tag — never a feature branch.
        assert '$CI_COMMIT_BRANCH == "main"' in rule_text
        assert '$CI_COMMIT_TAG' in rule_text

    def test_apply_uses_production_environment(self):
        _, doc = _render("aws")
        env = doc["terraform_apply"]["environment"]
        assert env["name"] == "production"

    def test_apply_runs_apply_from_tfplan_artifact(self):
        _, doc = _render("aws")
        script = "\n".join(doc["terraform_apply"]["script"])
        # It must consume the artifact produced by the plan job.
        assert "terraform apply -input=false -auto-approve tfplan" in script

    def test_apply_publishes_outputs_json(self):
        _, doc = _render("aws")
        art = doc["terraform_apply"]["artifacts"]
        assert any("outputs.json" in p for p in art["paths"])


class TestCloudSpecificAuth:
    def test_aws_uses_sts_get_caller_identity(self):
        _, doc = _render("aws")
        before = "\n".join(doc["terraform_validate"]["before_script"])
        assert "aws sts get-caller-identity" in before

    def test_azure_uses_service_principal_login(self):
        _, doc = _render("azure")
        before = "\n".join(doc["terraform_validate"]["before_script"])
        assert "az login --service-principal" in before

    def test_gcp_uses_service_account_activation(self):
        _, doc = _render("gcp")
        before = "\n".join(doc["terraform_validate"]["before_script"])
        assert "gcloud auth activate-service-account" in before


class TestAgentPoolTagsHonoured:
    def test_agent_pool_tags_applied_to_every_infra_job(self):
        _, doc = _render("aws", agent_pool="AIPP-Runners")
        for j in ("terraform_validate", "terraform_plan",
                  "terraform_policy", "terraform_apply"):
            assert doc[j].get("tags") == ["AIPP-Runners"], (
                f"job {j} missing agent_pool tags"
            )

    def test_no_tags_when_agent_pool_is_none(self):
        _, doc = _render("aws")
        for j in ("terraform_validate", "terraform_plan",
                  "terraform_policy", "terraform_apply"):
            assert "tags" not in doc[j], (
                f"job {j} unexpectedly has tags when agent_pool is None"
            )


class TestNonInfraStillUsesLegacyRender:
    def test_all_in_one_pipeline_does_not_short_circuit_to_infra(self):
        gen = GitLabCIGenerator(
            plan=_plan("aws"), env_plan=_env_prod(),
            tech=_tech(), repo_name="demo",
            pipeline_type="all_in_one",
        )
        text = gen.render()
        # Legacy render emits `container_build_scan_push`, infra flow does not.
        assert "container_build_scan_push" in text
        assert "terraform_apply" not in text


class TestHeaderComment:
    def test_first_line_documents_provider(self):
        text, _ = _render("azure")
        # A leading `# AIPP ...` block improves human readability.
        # The header now starts with a `# ===...===` separator; the
        # provider-description line lives within the first few lines.
        head = "\n".join(text.strip().splitlines()[:6])
        assert head.startswith("#")
        assert "Terraform" in head or "provider" in head
