"""Iteration-20 — every pipeline output (not just Terraform infra) must
carry inline `#` comments so the generated file reads top-to-bottom.

User feedback: "just now ran with other repo but comments are missing —
can you check all the pipelines should generate with comments like infra"
"""

from __future__ import annotations

import pytest

from backend.generators.azure_devops import AzureDevOpsGenerator
from backend.generators.github_actions import GitHubActionsGenerator
from backend.generators.gitlab_ci import GitLabCIGenerator
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


def _tech():
    return TechnologyProfile(
        language="javascript", framework="react", package_manager="npm",
        build_tool="vite", test_framework="vitest",
        container_ready=True, kubernetes_ready=False, helm_ready=False,
    )


def _plan(ci, cloud="azure"):
    return PipelinePlan(
        ci_platform=CIPlatform(ci), cloud_platform=CloudPlatform(cloud),
        stages=[PipelineStage(
            name="build", purpose="b", tools=["npm"],
            depends_on=[], optional=False, explanation="e",
        )],
        artifacts_strategy="a", security_strategy="s", approval_strategy="m",
        notifications=[], custom_requirement_addressed="",
    )


def _env_plan():
    return EnvironmentPlan(rules=[EnvironmentRule(
        name=EnvironmentName("production"), trigger="version_tag",
        requires_approval=True, health_check=True, smoke_test=True,
    )])


GENERATORS = [
    (AzureDevOpsGenerator, "azure_devops"),
    (GitHubActionsGenerator, "github_actions"),
    (GitLabCIGenerator, "gitlab_ci"),
    (HarnessGenerator, "harness"),
    (TektonGenerator, "tekton"),
]


@pytest.mark.parametrize("cls,ci", GENERATORS)
class TestNonInfraPipelinesAlsoHaveInlineComments:
    """The infra flow already carries STAGE comments — this suite makes sure
    the CI / all_in_one / build_only scopes are also self-documenting."""

    def _render(self, cls, ci, scope="all_in_one"):
        gen = cls(
            plan=_plan(ci), env_plan=_env_plan(), tech=_tech(),
            repo_name="medico-bloom", pipeline_type=scope,
        )
        return gen.render()

    def test_top_of_file_has_a_header_comment_block(self, cls, ci):
        text = self._render(cls, ci)
        head = "\n".join(text.strip().splitlines()[:5])
        assert head.startswith("#"), f"{ci}: expected leading `#` comment"
        assert "AIPP" in head, f"{ci}: header should mention AIPP"

    def test_at_least_one_stage_or_job_has_a_comment_above_it(self, cls, ci):
        text = self._render(cls, ci)
        # Count occurrences of the "STAGE · " / "JOB · " / "TASK · " marker.
        markers = ("STAGE ·", "JOB ·", "TASK ·")
        assert any(m in text for m in markers), (
            f"{ci}: no STAGE/JOB/TASK header comments found in non-infra output"
        )

    def test_pipeline_type_ci_also_has_comments(self, cls, ci):
        text = self._render(cls, ci, scope="ci")
        assert "AIPP-generated" in text or text.startswith("#")

    def test_pipeline_type_build_only_also_has_comments(self, cls, ci):
        text = self._render(cls, ci, scope="build_only")
        # build_only might emit only 1 stage — but the header must still be there.
        assert text.strip().startswith("#")

    def test_yaml_still_parses_after_comment_injection(self, cls, ci):
        import yaml
        text = self._render(cls, ci)
        body = "\n".join(l for l in text.splitlines()
                         if not l.lstrip().startswith("#"))
        if ci == "tekton":
            docs = list(yaml.safe_load_all(text))
            assert docs
        else:
            doc = yaml.safe_load(body)
            assert doc is not None
