"""Pipeline Generation Agent — turns a PipelinePlan + EnvironmentPlan into
concrete YAML for the requested CI/CD platform, using deterministic templates
under `backend/generators/`.
"""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.generators.azure_devops import AzureDevOpsGenerator
from backend.generators.github_actions import GitHubActionsGenerator
from backend.generators.gitlab_ci import GitLabCIGenerator
from backend.generators.harness import HarnessGenerator
from backend.generators.tekton import TektonGenerator
from backend.models.environment import EnvironmentPlan
from backend.models.pipeline import CIPlatform, GeneratedPipeline, PipelinePlan, TechnologyProfile

logger = get_logger(__name__)


class PipelineGenerationAgent:
    name = "pipeline_generation_agent"

    _map = {
        CIPlatform.github_actions: GitHubActionsGenerator,
        CIPlatform.azure_devops: AzureDevOpsGenerator,
        CIPlatform.gitlab_ci: GitLabCIGenerator,
        CIPlatform.harness: HarnessGenerator,
        CIPlatform.tekton: TektonGenerator,
    }

    def run(
        self,
        *,
        plan: PipelinePlan,
        env_plan: EnvironmentPlan,
        tech: TechnologyProfile,
        repo_name: str,
        pipeline_type: str = "all_in_one",
        agent_pool: str | None = None,
        custom_requirement: str | None = None,
    ) -> GeneratedPipeline:
        cls = self._map[plan.ci_platform]
        generator = cls(
            plan=plan, env_plan=env_plan, tech=tech, repo_name=repo_name,
            pipeline_type=pipeline_type, agent_pool=agent_pool,
            custom_requirement=custom_requirement,
        )
        yaml_content = generator.render()
        return GeneratedPipeline(
            ci_platform=plan.ci_platform,
            cloud_platform=plan.cloud_platform,
            filename=generator.filename,
            yaml_content=yaml_content,
            stage_explanations=[
                {"stage": s.name, "why": s.explanation, "tools": s.tools} for s in plan.stages
            ],
        )
