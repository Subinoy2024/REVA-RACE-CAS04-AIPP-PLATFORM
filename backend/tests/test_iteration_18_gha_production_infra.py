"""Iteration-18 regression tests — GitHub Actions gets the same
production-grade Terraform pipeline that iter-17 shipped for Azure DevOps,
and the UI label truthfully advertises what the infra scope produces.

User's requirement: "same approach for all the pipeline generators" —
the production infra pipeline (tflint / tfsec / OPA / Terratest / plan
artifact / manual approval / apply from artifact / outputs) must apply
consistently, starting with the two most-used platforms.
"""

from __future__ import annotations

import inspect

import yaml as _yaml

from backend.generators.github_actions import GitHubActionsGenerator
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
from frontend.tabs import pipeline_generator as pg


def _render_gha_infra(cloud: str = "azure",
                      pool: str | None = None) -> str:
    plan = PipelinePlan(
        ci_platform=CIPlatform.github_actions,
        cloud_platform=CloudPlatform(cloud),
        stages=[], artifacts_strategy="acr", security_strategy="trivy",
        approval_strategy="manual", notifications=[],
        custom_requirement_addressed="",
    )
    env = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.production, trigger="version_tag",
                        requires_approval=True),
    ])
    tech = TechnologyProfile(
        language="python", framework="fastapi", package_manager="pip",
        containerized=True, kubernetes_ready=False, test_frameworks=["pytest"],
        build_tools=[], notes=[],
    )
    return GitHubActionsGenerator(
        plan=plan, env_plan=env, tech=tech,
        repo_name="policy-as-code-terraform",
        pipeline_type="infra", agent_pool=pool,
    ).render()


def _doc(cloud: str = "azure", pool: str | None = None) -> dict:
    return _yaml.safe_load(_render_gha_infra(cloud, pool))


# ---------------------------------------------------------------------------
# 1. UI label reflects the new production flow
# ---------------------------------------------------------------------------
class TestUILabelAdvertisesProductionFlow:
    def test_infra_label_mentions_terraform_tools(self):
        labels = [lbl for lbl, val in pg.PIPELINE_TYPES if val == "infra"]
        assert labels, "infra scope missing from PIPELINE_TYPES"
        label = labels[0]
        # Truthful advertising — user picking `Infra only` should know what
        # they'll actually get.
        assert "production" in label.lower()
        for tool in ["tflint", "tfsec", "OPA", "Terratest", "approval"]:
            assert tool in label, (
                f"infra scope label doesn't mention `{tool}` — users won't "
                f"know it's part of the default pipeline"
            )

    def test_infra_label_no_longer_says_plan_apply_only(self):
        labels = [lbl for lbl, val in pg.PIPELINE_TYPES if val == "infra"]
        # Old lightweight description is gone.
        assert "plan + apply" not in labels[0]


# ---------------------------------------------------------------------------
# 2. GitHub Actions emits the same 4 jobs as ADO
# ---------------------------------------------------------------------------
class TestGithubActionsInfraHasFourProductionJobs:
    def test_jobs_are_validate_plan_policy_apply_in_order(self):
        doc = _doc("azure")
        job_ids = list(doc["jobs"].keys())
        assert job_ids == ["validate", "plan", "policy", "apply"]

    def test_dependency_chain_is_linear_validate_plan_policy_apply(self):
        doc = _doc("azure")
        assert "needs" not in doc["jobs"]["validate"]  # entry point
        assert doc["jobs"]["plan"]["needs"] == "validate"
        assert doc["jobs"]["policy"]["needs"] == "plan"
        assert doc["jobs"]["apply"]["needs"] == "policy"

    def test_apply_job_uses_production_environment(self):
        """GitHub Environments enforces required-reviewer approval —
        equivalent to ADO's Environments approval gate."""
        doc = _doc("azure")
        assert doc["jobs"]["apply"]["environment"] == "production"

    def test_apply_job_gated_by_branch_condition(self):
        doc = _doc("azure")
        cond = doc["jobs"]["apply"]["if"]
        assert "refs/heads/main" in cond
        assert "refs/tags/v" in cond


# ---------------------------------------------------------------------------
# 3. Each job installs / runs the right tools
# ---------------------------------------------------------------------------
class TestValidateJobToolChain:
    def test_installs_terraform_tflint_tfsec(self):
        yml = _render_gha_infra("azure")
        assert "hashicorp/setup-terraform@v3" in yml
        assert "terraform-linters/setup-tflint@v4" in yml
        assert "aquasecurity/tfsec-action" in yml

    def test_runs_fmt_check_and_validate(self):
        yml = _render_gha_infra("azure")
        assert "terraform fmt -check -recursive" in yml
        assert "terraform validate" in yml


class TestPlanJobPublishesArtifact:
    def test_plan_command_writes_tfplan_and_plan_json(self):
        yml = _render_gha_infra("azure")
        assert "-out=tfplan" in yml
        assert "terraform show -json tfplan > plan.json" in yml

    def test_plan_uploads_tfplan_artifact(self):
        doc = _doc("azure")
        steps = doc["jobs"]["plan"]["steps"]
        uploads = [s for s in steps
                   if isinstance(s, dict) and s.get("uses", "").startswith("actions/upload-artifact")]
        assert uploads, "plan job must upload the tfplan artifact"
        assert uploads[0]["with"]["name"] == "tfplan"


class TestPolicyJob:
    def test_downloads_tfplan_artifact(self):
        yml = _render_gha_infra("azure")
        assert "actions/download-artifact@v4" in yml

    def test_runs_conftest_and_terratest_soft_fail(self):
        yml = _render_gha_infra("azure")
        assert "conftest" in yml
        assert "go test" in yml
        # Soft-fail steps must have continue-on-error true so a missing
        # ./policy or ./tests directory doesn't tank the pipeline.
        doc = _doc("azure")
        opa_step = next(s for s in doc["jobs"]["policy"]["steps"]
                        if "gate" in str(s.get("name", "")).lower())
        assert opa_step.get("continue-on-error") is True
        terratest_step = next(s for s in doc["jobs"]["policy"]["steps"]
                              if "terratest" in str(s.get("name", "")).lower())
        assert terratest_step.get("continue-on-error") is True


class TestApplyJobConsumesArtifact:
    def test_apply_downloads_tfplan_and_does_not_re_plan(self):
        doc = _doc("azure")
        apply_steps = doc["jobs"]["apply"]["steps"]
        step_texts = _yaml.safe_dump(apply_steps)
        assert "download-artifact" in step_texts, (
            "apply must consume the tfplan artifact, not re-plan"
        )
        assert "terraform plan" not in step_texts, (
            "apply MUST NOT re-plan — it must apply the exact artifact "
            "that the human approved"
        )
        assert "terraform apply -input=false -auto-approve tfplan" in step_texts

    def test_apply_publishes_terraform_outputs(self):
        yml = _render_gha_infra("azure")
        assert "terraform output -json > outputs.json" in yml
        assert "terraform-outputs" in yml


# ---------------------------------------------------------------------------
# 4. Cloud auth is OIDC-based (uses id-token permission)
# ---------------------------------------------------------------------------
class TestCloudAuthPerCloud:
    def test_azure_login_step_present(self):
        yml = _render_gha_infra("azure")
        assert "azure/login" in yml

    def test_aws_login_step_present(self):
        yml = _render_gha_infra("aws")
        assert "aws-actions/configure-aws-credentials" in yml

    def test_gcp_login_step_present(self):
        yml = _render_gha_infra("gcp")
        assert "google-github-actions/auth" in yml

    def test_workflow_has_id_token_write_permission(self):
        doc = _doc("azure")
        assert doc["permissions"]["id-token"] == "write"


# ---------------------------------------------------------------------------
# 5. agent_pool still flows into every job (iter-16 invariant preserved)
# ---------------------------------------------------------------------------
class TestAgentPoolAppliesToInfraJobsToo:
    def test_no_pool_defaults_to_ubuntu(self):
        doc = _doc("azure")
        for job in doc["jobs"].values():
            assert job["runs-on"] == "ubuntu-22.04"

    def test_pool_switches_all_infra_jobs_to_self_hosted(self):
        doc = _doc("azure", pool="AIPP-Agents")
        for job_id, job in doc["jobs"].items():
            assert job["runs-on"] == ["self-hosted", "AIPP-Agents"], (
                f"infra job {job_id} did not honour agent_pool"
            )


# ---------------------------------------------------------------------------
# 6. YAML is parseable + non-infra scope is unaffected
# ---------------------------------------------------------------------------
class TestBackwardsCompatibility:
    def test_yaml_is_parseable_for_all_clouds(self):
        for cloud in ("azure", "aws", "gcp"):
            doc = _doc(cloud)
            assert isinstance(doc, dict)
            assert "jobs" in doc

    def test_non_infra_scope_still_uses_original_flow(self):
        """A CI-only render must NOT emit the terraform jobs — that would
        break the ci scope."""
        plan = PipelinePlan(
            ci_platform=CIPlatform.github_actions,
            cloud_platform=CloudPlatform.aws,
            stages=[], artifacts_strategy="acr", security_strategy="trivy",
            approval_strategy="manual", notifications=[],
            custom_requirement_addressed="",
        )
        env = EnvironmentPlan(rules=[
            EnvironmentRule(name=EnvironmentName.production, trigger="version_tag",
                            requires_approval=True),
        ])
        tech = TechnologyProfile(
            language="python", framework="fastapi", package_manager="pip",
            containerized=True, kubernetes_ready=False,
            test_frameworks=["pytest"], build_tools=[], notes=[],
        )
        yml = GitHubActionsGenerator(
            plan=plan, env_plan=env, tech=tech, repo_name="demo",
            pipeline_type="ci",
        ).render()
        assert "terraform" not in yml.lower()
        assert "build" in yml
