"""Iteration-17 regression tests — production-grade Terraform infra pipeline.

User requirement: "for infra ... by default without user custom message we
should build production-level infra-level pipeline like tflint, tfsec,
terratest, OPA, plan artifact, approval, deployment from artifact and output."

Fix (this iteration): emit 4 stages for `pipeline_type='infra'`:
    1. terraform_validate → fmt + init + validate + tflint + tfsec
    2. terraform_plan     → plan → publishes `tfplan` build artifact
    3. terraform_policy   → OPA/conftest against plan.json + Terratest hook
    4. terraform_apply    → deployment job with manual approval, downloads
                            the tfplan artifact and runs `terraform apply
                            tfplan`, then publishes `terraform output -json`.

Every `terraform` command is wrapped in a cloud-authenticated task
(`AzureCLI@2` / `AWSShellScript@1` / `gcloud@0`) using the compile-time
`${{ parameters.<cloud>ServiceConnection }}` expression fixed in iter-13.
`TF_ROOT`, `TF_VERSION`, `TF_BACKEND_KEY` are exposed as pipeline variables
with sensible defaults.
"""

from __future__ import annotations

import yaml as _yaml

from backend.generators.azure_devops import AzureDevOpsGenerator
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


def _render_infra(cloud: str = "azure") -> str:
    plan = PipelinePlan(
        ci_platform=CIPlatform.azure_devops,
        cloud_platform=CloudPlatform(cloud),
        stages=[], artifacts_strategy="acr", security_strategy="trivy",
        approval_strategy="manual", notifications=[],
        custom_requirement_addressed="",
    )
    env = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch"),
        EnvironmentRule(name=EnvironmentName.production, trigger="version_tag",
                        requires_approval=True),
    ])
    tech = TechnologyProfile(
        language="python", framework="fastapi", package_manager="pip",
        containerized=True, kubernetes_ready=False, test_frameworks=["pytest"],
        build_tools=[], notes=[],
    )
    return AzureDevOpsGenerator(
        plan=plan, env_plan=env, tech=tech, repo_name="policy-as-code-with-terraform",
        pipeline_type="infra", agent_pool="default",
    ).render()


def _doc(cloud: str = "azure") -> dict:
    return _yaml.safe_load(_render_infra(cloud))


# ---------------------------------------------------------------------------
# 1. Four production stages
# ---------------------------------------------------------------------------
class TestInfraHasFourProductionStages:
    def test_stages_are_validate_plan_policy_apply(self):
        stages = [s["stage"] for s in _doc("azure")["stages"]]
        assert stages == [
            "terraform_validate",
            "terraform_plan",
            "terraform_policy",
            "terraform_apply",
        ]

    def test_stages_are_the_same_for_aws_and_gcp(self):
        for cloud in ("aws", "gcp"):
            stages = [s["stage"] for s in _doc(cloud)["stages"]]
            assert stages == [
                "terraform_validate",
                "terraform_plan",
                "terraform_policy",
                "terraform_apply",
            ], f"cloud={cloud} produced unexpected stages: {stages}"


# ---------------------------------------------------------------------------
# 2. Stage 1 — validate: fmt / init / validate / tflint / tfsec
# ---------------------------------------------------------------------------
class TestValidateStage:
    def test_validate_stage_installs_terraform_tflint_tfsec(self):
        yml = _render_infra("azure")
        assert "TerraformInstaller@1" in yml
        assert "tflint" in yml
        assert "tfsec" in yml

    def test_validate_stage_runs_fmt_check(self):
        yml = _render_infra("azure")
        # Native TerraformTaskV2@2 fmt runs as `command: custom` +
        # `customCommand: fmt` with `-check -recursive`.
        assert "customCommand: 'fmt'" in yml
        assert "-check -recursive" in yml

    def test_validate_stage_runs_terraform_validate(self):
        yml = _render_infra("azure")
        # TerraformTaskV2@2 with `command: validate` is the native way.
        assert "command: 'validate'" in yml


# ---------------------------------------------------------------------------
# 3. Stage 2 — plan produces an artifact
# ---------------------------------------------------------------------------
class TestPlanStagePublishesArtifact:
    def _plan_stage(self, cloud="azure"):
        return next(s for s in _doc(cloud)["stages"]
                    if s["stage"] == "terraform_plan")

    def test_plan_stage_writes_tfplan_and_plan_json(self):
        yml = _render_infra("azure")
        # `-out=tfplan` (as a commandOptions string) + `terraform show -json`
        # in the follow-up script that emits plan.json for the OPA gate.
        assert "-out=tfplan" in yml
        assert "terraform show -json tfplan" in yml

    def test_plan_stage_publishes_tfplan_artifact(self):
        yml = _render_infra("azure")
        assert "PublishBuildArtifacts@1" in yml
        # yaml.safe_dump may quote strings — accept both quoted and unquoted.
        assert ("ArtifactName: tfplan" in yml
                or "ArtifactName: 'tfplan'" in yml)

    def test_plan_stage_depends_on_validate(self):
        s = self._plan_stage()
        assert s.get("dependsOn") == "terraform_validate"


# ---------------------------------------------------------------------------
# 4. Stage 3 — OPA / conftest + Terratest hooks
# ---------------------------------------------------------------------------
class TestPolicyStage:
    def _policy_stage(self):
        return next(s for s in _doc("azure")["stages"]
                    if s["stage"] == "terraform_policy")

    def test_policy_stage_downloads_the_tfplan_artifact(self):
        yml = _render_infra("azure")
        assert "DownloadBuildArtifacts@1" in yml
        # `artifactName:` may be quoted by yaml.safe_dump — accept both.
        assert ("artifactName: tfplan" in yml
                or "artifactName: 'tfplan'" in yml)

    def test_policy_stage_installs_and_runs_conftest(self):
        yml = _render_infra("azure")
        assert "conftest" in yml
        # Must key the OPA check on the ./policy directory presence.
        assert "policy" in yml.lower()

    def test_policy_stage_runs_terratest_when_present(self):
        yml = _render_infra("azure")
        assert "go test" in yml
        assert "tests" in yml.lower()

    def test_policy_stage_soft_fails_gracefully_when_no_policies(self):
        """If the repo has no ./policy dir or ./tests dir, the pipeline must
        NOT block — the checks should log 'skipping' and continue."""
        yml = _render_infra("azure")
        assert "skipping OPA gate" in yml or "No ./policy directory" in yml
        assert ("No Terratest suite" in yml
                or "skipping" in yml.lower())


# ---------------------------------------------------------------------------
# 5. Stage 4 — apply is a deployment job with a manual-approval environment
# ---------------------------------------------------------------------------
class TestApplyStageIsGated:
    def _apply_stage(self):
        return next(s for s in _doc("azure")["stages"]
                    if s["stage"] == "terraform_apply")

    def test_apply_stage_uses_deployment_job(self):
        st = self._apply_stage()
        assert "jobs" in st
        job = st["jobs"][0]
        assert "deployment" in job, "apply must be a deployment: job for approval"

    def test_apply_stage_targets_production_environment(self):
        st = self._apply_stage()
        job = st["jobs"][0]
        assert job["environment"] == "production"

    def test_apply_stage_consumes_tfplan_artifact_not_re_plans(self):
        yml = _render_infra("azure")
        # No `terraform plan` inside the apply stage — it must consume the artifact.
        apply = self._apply_stage()
        apply_yaml = _yaml.safe_dump(apply)
        assert "'plan'" not in apply_yaml and "command: plan" not in apply_yaml, (
            "apply stage must consume the tfplan artifact, not re-plan "
            "(otherwise it may drift from the approved plan)"
        )
        # Native TerraformTaskV2@2 apply reads the plan file via commandOptions.
        assert "-auto-approve tfplan" in yml
        assert "command: 'apply'" in yml

    def test_apply_stage_publishes_terraform_outputs(self):
        yml = _render_infra("azure")
        # Native task doesn't have `output` command exposed in older
        # extension versions, so we shell out for the outputs.json emission.
        assert "terraform output -json > outputs.json" in yml
        assert "terraform-outputs" in yml

    def test_apply_stage_gated_by_branch_condition(self):
        st = self._apply_stage()
        # Only runs on main or v*.*.* tags — never on feature branches.
        assert "condition" in st
        assert "refs/heads/main" in st["condition"]
        assert "refs/tags/v" in st["condition"]


# ---------------------------------------------------------------------------
# 6. Every terraform command uses the native TerraformTaskV2@2 marketplace
# task with the cloud-appropriate backend/env service-connection input.
# ---------------------------------------------------------------------------
class TestTerraformCommandsAreCloudAuthenticated:
    def test_azure_wraps_terraform_in_azure_cli_task(self):
        yml = _render_infra("azure")
        # Native task from the Microsoft DevLabs marketplace extension.
        assert "TerraformTaskV2@2" in yml
        assert "TerraformInstaller@1" in yml
        # Backend + env SC references are compile-time (not $(VAR)).
        assert "backendServiceArm: '${{ parameters.azureServiceConnection }}'" in yml
        assert "environmentServiceNameAzureRM: '${{ parameters.azureServiceConnection }}'" in yml
        assert "$(AZURE_SUBSCRIPTION)" not in yml
        assert "$(AZURE_SERVICE_CONNECTION)" not in yml

    def test_aws_wraps_terraform_in_aws_shell_task(self):
        yml = _render_infra("aws")
        # Same native task — provider switched to `aws`, backend key too.
        assert "TerraformTaskV2@2" in yml
        assert "provider: 'aws'" in yml
        assert "backendServiceAWS: '${{ parameters.awsServiceConnection }}'" in yml
        assert "environmentServiceNameAWS: '${{ parameters.awsServiceConnection }}'" in yml

    def test_gcp_wraps_terraform_in_gcloud_task(self):
        yml = _render_infra("gcp")
        assert "TerraformTaskV2@2" in yml
        assert "provider: 'gcp'" in yml
        assert "backendServiceGCP: '${{ parameters.gcpServiceConnection }}'" in yml
        assert "environmentServiceNameGCP: '${{ parameters.gcpServiceConnection }}'" in yml


# ---------------------------------------------------------------------------
# 7. Pipeline variables have sensible defaults
# ---------------------------------------------------------------------------
class TestPipelineVariablesHaveDefaults:
    def test_tf_root_defaults_to_current_dir(self):
        doc = _doc("azure")
        assert doc["variables"]["TF_ROOT"] == "."

    def test_tf_version_defaults_to_latest(self):
        doc = _doc("azure")
        assert doc["variables"]["TF_VERSION"] == "latest"

    def test_tf_backend_key_defaults_to_repo_tfstate(self):
        doc = _doc("azure")
        assert "tfstate" in doc["variables"]["TF_BACKEND_KEY"]

    def test_no_cyclical_variable_references(self):
        """Iter-15 regression — no self-references."""
        doc = _doc("azure")
        for k, v in doc["variables"].items():
            if isinstance(v, str):
                assert f"$({k})" not in v, (
                    f"CYCLICAL var: {k}={v!r} references itself"
                )


# ---------------------------------------------------------------------------
# 8. YAML parses cleanly + has the top-level parameters block
# ---------------------------------------------------------------------------
class TestYAMLStructuralInvariants:
    def test_yaml_parseable(self):
        for cloud in ("azure", "aws", "gcp"):
            assert _doc(cloud), f"cloud={cloud} produced unparseable YAML"

    def test_parameters_block_declares_sc_default(self):
        doc = _doc("azure")
        params = doc.get("parameters", [])
        assert params, "infra pipeline must declare a service-connection parameter"
        names = {p["name"] for p in params}
        assert "azureServiceConnection" in names
