"""Iteration-13 regression tests — ADO service-connection references must be
compile-time (`${{ parameters.X }}`), never runtime `$(VAR)`.

Bug reported by the user:
  ADO rejected the generated `azure-pipelines.yml` in <1 second with:
      "Job container: Step AzureCLI input connectedServiceNameARM references
       service connection $(AZURE_SUBSCRIPTION) which could not be found."
      "Job deploy_development: Step input azureSubscription references
       service connection $(AZURE_SERVICE_CONNECTION) which could not be found."

Root cause:
  Service-connection fields on Azure Pipelines tasks (`azureSubscription`,
  `awsCredentials`, `connectedServiceNameARM`) are resolved at pipeline
  COMPILE time. Runtime `$(VAR)` syntax is not supported for these fields.

Fix:
  1. Emit a top-level `parameters:` block with the SC name as a `string`
     parameter and a sensible default.
  2. Use `${{ parameters.<cloud>ServiceConnection }}` at every SC reference.
  3. Update setup instructions to tell the user to name the connection
     exactly `azure-service-connection` (matching the default).
"""

from __future__ import annotations

import re

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _mk_plan(cloud: str) -> PipelinePlan:
    return PipelinePlan(
        ci_platform=CIPlatform.azure_devops,
        cloud_platform=CloudPlatform(cloud),
        stages=[], artifacts_strategy="acr", security_strategy="trivy",
        approval_strategy="manual", notifications=[],
        custom_requirement_addressed="",
    )


def _mk_env_plan() -> EnvironmentPlan:
    return EnvironmentPlan(rules=[
        EnvironmentRule(
            name=EnvironmentName.development, trigger="develop_branch",
            health_check=True, smoke_test=True,
        ),
        EnvironmentRule(
            name=EnvironmentName.production, trigger="version_tag",
            requires_approval=True, health_check=True, smoke_test=True,
        ),
    ])


def _mk_tech() -> TechnologyProfile:
    return TechnologyProfile(
        language="python", framework="fastapi", package_manager="pip",
        containerized=True, kubernetes_ready=False, test_frameworks=["pytest"],
        build_tools=[], notes=[],
    )


def _render(cloud: str) -> str:
    gen = AzureDevOpsGenerator(
        plan=_mk_plan(cloud), env_plan=_mk_env_plan(),
        tech=_mk_tech(), repo_name="demo-app",
    )
    return gen.render()


# ---------------------------------------------------------------------------
# 1. `parameters:` block is emitted for every cloud
# ---------------------------------------------------------------------------
class TestParametersBlock:
    def test_azure_emits_azure_sc_parameter(self):
        doc = yaml.safe_load(_render("azure"))
        params = doc.get("parameters", [])
        assert params, "no parameters: block emitted for cloud=azure"
        names = {p["name"] for p in params}
        assert "azureServiceConnection" in names

    def test_aws_emits_aws_sc_parameter(self):
        doc = yaml.safe_load(_render("aws"))
        names = {p["name"] for p in doc.get("parameters", [])}
        assert "awsServiceConnection" in names

    def test_gcp_emits_gcp_sc_parameter(self):
        doc = yaml.safe_load(_render("gcp"))
        names = {p["name"] for p in doc.get("parameters", [])}
        assert "gcpServiceConnection" in names

    def test_parameter_default_matches_docs(self):
        for cloud, expected in [("azure", "azure-service-connection"),
                                ("aws", "aws-service-connection"),
                                ("gcp", "gcp-service-connection")]:
            doc = yaml.safe_load(_render(cloud))
            params = doc.get("parameters", [])
            defaults = [p.get("default") for p in params]
            assert expected in defaults, (
                f"cloud={cloud} default parameter should be {expected}, got {defaults}"
            )

    def test_parameter_type_is_string(self):
        doc = yaml.safe_load(_render("azure"))
        for p in doc.get("parameters", []):
            assert p.get("type") == "string", (
                f"parameter {p} must be typed as `string` for ADO"
            )


# ---------------------------------------------------------------------------
# 2. No runtime $(...) SC references anywhere in the YAML
# ---------------------------------------------------------------------------
class TestNoRuntimeServiceConnectionReferences:
    BANNED_RUNTIME_REFS = [
        "$(AZURE_SERVICE_CONNECTION)",
        "$(AZURE_SUBSCRIPTION)",   # ACR-login regression
        "$(AWS_SERVICE_CONNECTION)",
        "$(GCP_SERVICE_CONNECTION)",
    ]

    def test_azure_yaml_has_no_banned_runtime_refs(self):
        yml = _render("azure")
        for banned in self.BANNED_RUNTIME_REFS:
            assert banned not in yml, (
                f"azure YAML must not use runtime `{banned}` — ADO resolves "
                f"service-connection references at compile time."
            )

    def test_aws_yaml_has_no_banned_runtime_refs(self):
        yml = _render("aws")
        for banned in self.BANNED_RUNTIME_REFS:
            assert banned not in yml

    def test_gcp_yaml_has_no_banned_runtime_refs(self):
        yml = _render("gcp")
        for banned in self.BANNED_RUNTIME_REFS:
            assert banned not in yml


# ---------------------------------------------------------------------------
# 3. Registry login step is cloud-aware and uses the compile-time parameter
# ---------------------------------------------------------------------------
class TestRegistryLoginPerCloud:
    def _package_steps(self, yml: str):
        doc = yaml.safe_load(yml)
        pkg = [s for s in doc["stages"] if s.get("stage") == "package"][0]
        return pkg["jobs"][0]["steps"]

    def test_azure_registry_login_uses_acr_and_compile_time_sc(self):
        steps = self._package_steps(_render("azure"))
        login = [s for s in steps if s.get("displayName") == "Log in to ACR"]
        assert login, "azure package stage missing 'Log in to ACR' step"
        login = login[0]
        assert login["task"] == "AzureCLI@2"
        assert login["inputs"]["azureSubscription"] == \
            "${{ parameters.azureServiceConnection }}"

    def test_aws_registry_login_uses_ecr_and_compile_time_sc(self):
        steps = self._package_steps(_render("aws"))
        login = [s for s in steps if s.get("displayName") == "Log in to ECR"]
        assert login, "aws package stage missing 'Log in to ECR' step"
        login = login[0]
        assert login["task"] == "AWSShellScript@1"
        assert login["inputs"]["awsCredentials"] == \
            "${{ parameters.awsServiceConnection }}"
        assert "aws ecr get-login-password" in login["inputs"]["inlineScript"]

    def test_gcp_registry_login_uses_gcloud_and_compile_time_sc(self):
        steps = self._package_steps(_render("gcp"))
        login = [s for s in steps
                 if s.get("displayName") == "Log in to Artifact Registry"]
        assert login, "gcp package stage missing 'Log in to Artifact Registry' step"
        login = login[0]
        assert login["task"] == "gcloud@0"
        assert login["inputs"]["connectedServiceNameARM"] == \
            "${{ parameters.gcpServiceConnection }}"


# ---------------------------------------------------------------------------
# 4. Deploy steps use compile-time parameter for the SC field
# ---------------------------------------------------------------------------
class TestDeployStepsCompileTimeSC:
    def _deploy_first_step(self, yml: str):
        doc = yaml.safe_load(yml)
        deploy = [s for s in doc["stages"]
                  if str(s.get("stage", "")).startswith("deploy_")][0]
        return deploy["jobs"][0]["strategy"]["runOnce"]["deploy"]["steps"][0]

    def test_azure_deploy_uses_compile_time_sc(self):
        step = self._deploy_first_step(_render("azure"))
        assert step["task"] == "AzureCLI@2"
        assert step["inputs"]["azureSubscription"] == \
            "${{ parameters.azureServiceConnection }}"

    def test_aws_deploy_uses_compile_time_sc(self):
        step = self._deploy_first_step(_render("aws"))
        assert step["task"] == "AWSShellScript@1"
        assert step["inputs"]["awsCredentials"] == \
            "${{ parameters.awsServiceConnection }}"

    def test_gcp_deploy_uses_compile_time_sc(self):
        step = self._deploy_first_step(_render("gcp"))
        assert step["task"] == "gcloud@0"
        assert step["inputs"]["connectedServiceNameARM"] == \
            "${{ parameters.gcpServiceConnection }}"


# ---------------------------------------------------------------------------
# 5. YAML is still valid + top-level ordering is sensible
# ---------------------------------------------------------------------------
class TestYAMLStructure:
    def test_yaml_is_parseable(self):
        for cloud in ("azure", "aws", "gcp"):
            yml = _render(cloud)
            assert yaml.safe_load(yml), f"cloud={cloud} produced unparseable YAML"

    def test_parameters_appear_before_trigger(self):
        """`parameters:` must come before `trigger:` for ADO to see it."""
        yml = _render("azure")
        p_idx = yml.find("parameters:")
        t_idx = yml.find("trigger:")
        assert p_idx != -1 and t_idx != -1
        assert p_idx < t_idx, (
            f"parameters: (at {p_idx}) must come before trigger: (at {t_idx})"
        )

    def test_every_service_connection_field_uses_parameter_expression(self):
        """Regex sweep: every SC field must use `${{ parameters.X }}`."""
        pattern = re.compile(
            r"(azureSubscription|awsCredentials|connectedServiceNameARM)\s*:\s*"
            r"([^\n]+)"
        )
        for cloud in ("azure", "aws", "gcp"):
            yml = _render(cloud)
            for match in pattern.finditer(yml):
                field, value = match.group(1), match.group(2).strip()
                # `connectedServiceNameSelector` isn't the SC field itself —
                # skip its unrelated values like 'connectedServiceNameARM'.
                if value in ("connectedServiceNameARM",):
                    continue
                assert value.startswith("${{ parameters."), (
                    f"[cloud={cloud}] {field}: {value!r} — must be a "
                    f"compile-time `${{{{ parameters.X }}}}` expression."
                )
