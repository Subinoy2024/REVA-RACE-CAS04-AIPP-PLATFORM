"""Iteration-26.3 · Honour Custom Deployment Requirement — python-only mode.

Reproduces the demo bug: user typed "python only, don't use azure cli" into
the Custom Deployment Requirement box, but the emitted Azure DevOps YAML
still contained `AzureCLI@2` + `az login` / `az webapp` commands.

Fix under test:
  * `parse_deploy_style()` detects the directive.
  * `BaseGenerator` propagates `custom_requirement` -> `self.deploy_style`.
  * `AzureDevOpsGenerator._wrap_deploy_steps()` swaps `AzureCLI@2` for a
    Python-SDK based `UsePythonVersion@0` + `pip install azure-mgmt-*` +
    `python -c` block when `deploy_style == "python"`.
"""

from __future__ import annotations

import yaml

from backend.generators.base import parse_deploy_style
from backend.generators.azure_devops import AzureDevOpsGenerator
from backend.generators.deploy_targets import AZURE_APP_SERVICE, AZURE_AKS
from backend.models.environment import EnvironmentPlan, EnvironmentRule, EnvironmentName
from backend.models.pipeline import (
    CIPlatform, CloudPlatform, PipelinePlan, PipelineStage, TechnologyProfile
)


# ---------- parser ---------------------------------------------------------

def test_parser_detects_no_cli_variants():
    for text in [
        "please use python only and no az cli",
        "I want only python script if needed otherwise use azure devops assistance only for the pipeline don't used azure cli also",
        "no azure cli, python only",
        "avoid az cli",
        "USE PYTHON ONLY",
    ]:
        assert parse_deploy_style(text) == "python", f"missed: {text!r}"


def test_parser_defaults_to_cli():
    assert parse_deploy_style("") == "cli"
    assert parse_deploy_style(None) == "cli"
    assert parse_deploy_style("deploy to AKS with helm, skip trivy") == "cli"


# ---------- DeployTarget commands_for --------------------------------------

def test_azure_app_service_swaps_commands_for_python():
    cli = AZURE_APP_SERVICE.commands_for("cli")
    py  = AZURE_APP_SERVICE.commands_for("python")
    assert any("az login" in c for c in cli)
    assert not any("az login" in c for c in py)
    assert any("WebSiteManagementClient" in c for c in py)


def test_azure_aks_swaps_commands_for_python():
    py = AZURE_AKS.commands_for("python")
    assert not any("az login" in c for c in py)
    assert not any("az aks get-credentials" in c for c in py)
    assert any("ContainerServiceClient" in c for c in py)


# ---------- End-to-end: generator omits AzureCLI@2 in python mode ---------

def _make_plan_env_tech(cloud: str = "azure"):
    stages = [
        PipelineStage(name="build", purpose="build", tools=["maven"], explanation="build"),
        PipelineStage(name="deploy_dev", purpose="deploy", tools=[], explanation="deploy"),
    ]
    plan = PipelinePlan(
        ci_platform=CIPlatform.azure_devops,
        cloud_platform=CloudPlatform.azure,
        stages=stages,
        deployment_target="azure_app_service",
    )
    env_plan = EnvironmentPlan(
        rules=[EnvironmentRule(
            name=EnvironmentName.development,
            trigger="main_branch",
            health_check=True,
            smoke_test=True,
        )],
    )
    tech = TechnologyProfile(language="python", framework="flask")
    return plan, env_plan, tech


def test_azure_devops_yaml_uses_cli_when_no_directive():
    plan, env_plan, tech = _make_plan_env_tech()
    gen = AzureDevOpsGenerator(
        plan=plan, env_plan=env_plan, tech=tech, repo_name="demo",
        pipeline_type="all_in_one",
    )
    ytext = gen.render()
    assert "AzureCLI@2" in ytext
    assert "az login" in ytext
    assert gen.deploy_style == "cli"


def test_azure_devops_yaml_uses_python_when_user_forbids_cli():
    plan, env_plan, tech = _make_plan_env_tech()
    gen = AzureDevOpsGenerator(
        plan=plan, env_plan=env_plan, tech=tech, repo_name="demo",
        pipeline_type="all_in_one",
        custom_requirement=(
            "i want only python script if needed otherwise use azure devops "
            "assistance only for the pipeline don't used azure cli also"
        ),
    )
    ytext = gen.render()
    assert gen.deploy_style == "python"
    # DEPLOY stage must NOT contain any `az` deploy commands.
    assert "az login --service-principal" not in ytext
    assert "az webapp" not in ytext
    assert "az aks get-credentials" not in ytext
    # SHOULD contain the Python-SDK path in the deploy stage.
    assert "UsePythonVersion@0" in ytext
    assert "azure-mgmt-web" in ytext
    assert "WebSiteManagementClient" in ytext
    # And should be valid YAML.
    yaml.safe_load(ytext)
