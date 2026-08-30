"""Unit tests for the YAML generators — deterministic, no LLM."""

from __future__ import annotations

import yaml

from backend.generators.azure_devops import AzureDevOpsGenerator
from backend.generators.github_actions import GitHubActionsGenerator
from backend.generators.gitlab_ci import GitLabCIGenerator
from backend.generators.harness import HarnessGenerator
from backend.generators.tekton import TektonGenerator
from backend.models.environment import (
    DeploymentStrategy,
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


def _fixture(ci: CIPlatform, cloud: CloudPlatform = CloudPlatform.azure):
    plan = PipelinePlan(
        ci_platform=ci, cloud_platform=cloud,
        stages=[
            PipelineStage(name="build", purpose="compile", tools=["poetry"], explanation="prep artifact"),
            PipelineStage(name="unit_test", purpose="verify", tools=["pytest"], explanation="test"),
            PipelineStage(name="container_build", purpose="pack", tools=["docker"], explanation="package"),
        ],
        artifacts_strategy="push to registry",
        security_strategy="trivy",
        approval_strategy="prod manual",
        notifications=["slack"],
        custom_requirement_addressed="none",
    )
    env = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch",
                        deployment_strategy=DeploymentStrategy.rolling, explanation="dev auto"),
        EnvironmentRule(name=EnvironmentName.qa, trigger="release_branch",
                        deployment_strategy=DeploymentStrategy.rolling, explanation="qa auto"),
        EnvironmentRule(name=EnvironmentName.staging, trigger="main_branch", requires_approval=True,
                        deployment_strategy=DeploymentStrategy.blue_green, explanation="staging gated"),
        EnvironmentRule(name=EnvironmentName.production, trigger="version_tag", requires_approval=True,
                        deployment_strategy=DeploymentStrategy.blue_green, explanation="prod gated"),
    ])
    tech = TechnologyProfile(language="python", build_tool="poetry", test_framework="pytest",
                             package_manager="poetry", container_ready=True)
    return plan, env, tech


def _parse(text: str):
    return list(yaml.safe_load_all(text))


def test_github_actions_generator():
    plan, env, tech = _fixture(CIPlatform.github_actions)
    yml = GitHubActionsGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render()
    docs = _parse(yml)
    assert docs and "jobs" in docs[0]
    assert "deploy_development" in docs[0]["jobs"]
    assert "deploy_production" in docs[0]["jobs"]


def test_azure_devops_generator():
    plan, env, tech = _fixture(CIPlatform.azure_devops)
    yml = AzureDevOpsGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render()
    doc = _parse(yml)[0]
    assert "stages" in doc
    stage_ids = [s["stage"] for s in doc["stages"]]
    assert "deploy_production" in stage_ids


def test_gitlab_ci_generator():
    plan, env, tech = _fixture(CIPlatform.gitlab_ci)
    yml = GitLabCIGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render()
    doc = _parse(yml)[0]
    assert "stages" in doc
    assert "deploy_production" in doc["stages"]
    assert doc["deploy_production"]["when"] == "manual"


def test_harness_generator():
    plan, env, tech = _fixture(CIPlatform.harness)
    yml = HarnessGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render()
    doc = _parse(yml)[0]
    assert "pipeline" in doc


def test_tekton_generator():
    plan, env, tech = _fixture(CIPlatform.tekton)
    yml = TektonGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render()
    docs = _parse(yml)
    kinds = {d["kind"] for d in docs if isinstance(d, dict)}
    assert "Task" in kinds and "Pipeline" in kinds
