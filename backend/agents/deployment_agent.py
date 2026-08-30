"""Environment Deployment Agent — chooses trigger + approval rules for
Development/QA/Staging/Production and explains every rule.
"""

from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.models.environment import EnvironmentPlan
from backend.models.pipeline import CIPlatform, CloudPlatform, PipelinePlan

SYSTEM = """You are the AIPP Environment Deployment Agent.
Given a pipeline plan, define trigger rules for four environments:
Development, QA, Staging, Production.

STRICT VALUE RULES (return only these exact literals):

* `trigger` must be one of:
    "feature_branch", "develop_branch", "release_branch",
    "main_branch", "version_tag", "manual"
  Do NOT put a glob or branch pattern here. The glob goes in
  `branch_pattern`.

* `deployment_strategy` must be one of:
    "rolling", "blue_green", "canary", "recreate"
  Do NOT invent new values like "gated" or "approval". Whether the
  deploy needs approval is expressed by `requires_approval: true`,
  not by the strategy field.

* `branch_pattern` is a free-text glob (e.g. "release/*", "main",
  "v*.*.*").

Default policy (adapt if the custom requirement demands otherwise):

  - feature branches        -> validation only (no deploy)
  - develop branch          -> automatic Development deploy
                               trigger=develop_branch, branch_pattern=develop
  - release branches        -> QA deploy
                               trigger=release_branch, branch_pattern=release/*,
                               requires_approval may be true
  - main branch             -> Staging deploy, approval required
                               trigger=main_branch, branch_pattern=main
  - version tag             -> Production deploy, approval required
                               trigger=version_tag, branch_pattern=v*.*.*
"""


class EnvironmentDeploymentAgent(BaseAgent[EnvironmentPlan]):
    name = "environment_deployment_agent"
    response_model = EnvironmentPlan

    def __init__(self) -> None:
        super().__init__(system_prompt=SYSTEM)

    def _build_prompt(self, *, plan: PipelinePlan) -> str:
        return f"""Pipeline plan summary:
- CI/CD: {plan.ci_platform.value}
- Cloud: {plan.cloud_platform.value}
- Stages: {[s.name for s in plan.stages]}
- Approval strategy: {plan.approval_strategy}
- Custom requirement addressed: {plan.custom_requirement_addressed}

Return JSON matching EnvironmentPlan:
{{
  "rules": [
    {{
      "name": "development",
      "trigger": "develop_branch",
      "branch_pattern": "develop",
      "requires_approval": false,
      "approvers": [],
      "deployment_strategy": "rolling",
      "health_check": true,
      "smoke_test": true,
      "rollback": true,
      "variables": ["APP_ENV=dev"],
      "secrets": ["REGISTRY_TOKEN"],
      "explanation": "..."
    }}
    // repeat for qa, staging, production
  ],
  "summary": "one-paragraph explanation of the whole environment strategy"
}}
"""
