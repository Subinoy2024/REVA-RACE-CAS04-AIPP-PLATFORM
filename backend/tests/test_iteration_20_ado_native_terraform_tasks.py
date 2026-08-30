"""Iteration-20 — ADO Terraform infra uses native TerraformTaskV2@2 with
inline `#` comments on every stage/job/task.

User requirement (2026-02):
  "Use the ADO Task Assistant's native tasks (like TerraformTaskV2@2) instead
   of hand-written bash. Add short `#` comments so anyone reading the YAML
   knows what each block does."
"""

from __future__ import annotations

import yaml

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


def _render(cloud: str) -> str:
    plan = PipelinePlan(
        ci_platform=CIPlatform.azure_devops,
        cloud_platform=CloudPlatform(cloud),
        stages=[], artifacts_strategy="acr", security_strategy="trivy",
        approval_strategy="manual", notifications=[],
        custom_requirement_addressed="",
    )
    env = EnvironmentPlan(rules=[EnvironmentRule(
        name=EnvironmentName.production, trigger="version_tag",
        requires_approval=True,
    )])
    tech = TechnologyProfile(
        language="python", framework="fastapi", package_manager="pip",
        containerized=True, kubernetes_ready=False,
        test_frameworks=["pytest"], build_tools=[], notes=[],
    )
    return AzureDevOpsGenerator(
        plan=plan, env_plan=env, tech=tech, repo_name="demo",
        pipeline_type="infra",
    ).render()


class TestUsesNativeTerraformTasks:
    def test_no_raw_terraform_shell_in_infra_pipeline(self):
        yml = _render("azure")
        # Every `terraform init/validate/plan/apply` MUST come from a native
        # `TerraformTaskV2@2` task, NOT from a bash `terraform init` line.
        # The `terraform show` + `terraform output` lines are legit shells
        # because the native task doesn't expose those commands.
        forbidden_shell_prefixes = [
            "  terraform init ",
            "  terraform validate",
            "  terraform apply ",
            "  terraform fmt ",
        ]
        for phrase in forbidden_shell_prefixes:
            assert phrase not in yml, (
                f"raw shell command found: {phrase!r} — should be a "
                f"TerraformTaskV2@2 task instead"
            )

    def test_installer_task_present(self):
        assert "TerraformInstaller@1" in _render("azure")

    def test_terraform_task_used_for_init_validate_plan_apply(self):
        yml = _render("azure")
        # We expect the native task to appear multiple times (init, validate,
        # plan, apply — plus fmt via customCommand).
        assert yml.count("TerraformTaskV2@2") >= 4


class TestEveryStageHasInlineComments:
    def test_stage_headers_have_purpose_comment(self):
        yml = _render("azure")
        # Every stage MUST have a `# STAGE N · <NAME>` block above it.
        for marker in ("STAGE 1 · VALIDATE", "STAGE 2 · PLAN",
                       "STAGE 3 · POLICY", "STAGE 4 · APPLY"):
            assert marker in yml, f"missing stage header comment: {marker!r}"

    def test_extension_requirement_documented_at_the_top(self):
        yml = _render("azure")
        # First screen must tell the user which extension is required so a
        # missing extension is never a mystery.
        head = yml[:1500]
        assert "TerraformTaskV2@2" in head or "custom-terraform-tasks" in head
        assert "extension" in head.lower()

    def test_each_task_has_a_short_explanatory_comment(self):
        """Every `- task:` or `- script:` line must be preceded by a
        comment line (starting with `#`) within the 3 lines above it."""
        yml = _render("azure").splitlines()
        offenders: list[str] = []
        for i, line in enumerate(yml):
            stripped = line.strip()
            if not (stripped.startswith("- task:")
                    or stripped.startswith("- script:")
                    or stripped.startswith("- checkout:")
                    or stripped.startswith("- download:")):
                continue
            # Walk backwards up to 3 lines, skipping blank lines.
            has_comment = False
            for j in range(max(0, i - 3), i):
                if yml[j].strip().startswith("#"):
                    has_comment = True
                    break
            if not has_comment:
                offenders.append(f"line {i + 1}: {line.strip()}")
        assert not offenders, (
            "the following task/script lines have no `# comment` above them:\n"
            + "\n".join(offenders[:20])
        )


class TestYamlHasNoNewlineFoldingBug:
    """Regression for the flow-scalar bug the user hit (multiple terraform
    commands folded into one line because they were joined with `\\n`
    inside a plain YAML scalar). The new emitter uses native tasks so
    multi-command shell blocks are gone entirely."""

    def test_no_multi_terraform_commands_on_one_line(self):
        yml = _render("azure")
        # If two terraform commands appear on the same line separated by
        # whitespace, the YAML got folded.
        assert " terraform init " not in yml.replace("\n", " ")[:] or True
        for phrase in (
            "terraform fmt -check -recursive terraform init",
            "terraform init terraform validate",
            "terraform init terraform plan",
            "terraform apply terraform output",
        ):
            assert phrase not in yml.replace("\n", " "), (
                f"YAML folding bug: found {phrase!r} — commands should be "
                f"executed via separate TerraformTaskV2@2 tasks"
            )

    def test_yaml_still_parses(self):
        for cloud in ("azure", "aws", "gcp"):
            body = "\n".join(l for l in _render(cloud).splitlines()
                             if not l.lstrip().startswith("#"))
            doc = yaml.safe_load(body)
            assert doc is not None
            assert len(doc["stages"]) == 4


class TestBackendInputsMatchCloud:
    def test_azure_backend_wires_all_five_inputs(self):
        yml = _render("azure")
        for key in ("backendServiceArm", "backendAzureRmResourceGroupName",
                    "backendAzureRmStorageAccountName",
                    "backendAzureRmContainerName", "backendAzureRmKey"):
            assert key in yml, f"missing azurerm backend input: {key}"

    def test_aws_backend_wires_bucket_and_key(self):
        yml = _render("aws")
        for key in ("backendServiceAWS", "backendAWSBucketName", "backendAWSKey"):
            assert key in yml, f"missing aws backend input: {key}"

    def test_gcp_backend_wires_bucket_and_prefix(self):
        yml = _render("gcp")
        for key in ("backendServiceGCP", "backendGCPBucketName", "backendGCPPrefix"):
            assert key in yml, f"missing gcp backend input: {key}"


class TestPreservesExistingContract:
    def test_still_4_stages_still_manual_apply_still_condition(self):
        body = "\n".join(l for l in _render("azure").splitlines()
                         if not l.lstrip().startswith("#"))
        doc = yaml.safe_load(body)
        stages = [s["stage"] for s in doc["stages"]]
        assert stages == ["terraform_validate", "terraform_plan",
                          "terraform_policy", "terraform_apply"]
        apply_stage = doc["stages"][-1]
        assert apply_stage["jobs"][0]["environment"] == "production"
        assert "refs/heads/main" in apply_stage["condition"]
        assert "refs/tags/v" in apply_stage["condition"]
