"""Iteration-20 regression tests — Terraform is default for all clouds,
Bicep is available as an explicit opt-in escape hatch (Azure only).

Requirements verified here:
  1. `_sanitize_iac(plan)` (no ``allow_bicep``) still rewrites Bicep to
     Terraform — this is the safe default and covers AWS/GCP.
  2. `_sanitize_iac(plan, allow_bicep=True)` keeps Bicep on the stage
     (Azure opt-in). Other forbidden IaCs (CF/CDK/SAM/Pulumi/DM) still get
     rewritten.
  3. `PipelinePlanningAgent.run()` only enables the opt-in when both
     ``iac_tool == "bicep"`` and ``cloud == azure``. AWS + iac_tool=bicep
     must still yield Terraform.
  4. The frontend directive builder emits Bicep guidance only for the
     Azure + bicep combo; every other combo emits the Terraform infra
     directive.
"""

from __future__ import annotations

import inspect

import pytest

from backend.agents.pipeline_planner import (
    PipelinePlanningAgent,
    _sanitize_iac,
    _FORBIDDEN_IAC_TOOLS,
)
from backend.models.pipeline import (
    CIPlatform,
    CloudPlatform,
    PipelinePlan,
    PipelineStage,
)


def _plan(tools, cloud="azure"):
    return PipelinePlan(
        ci_platform=CIPlatform("azure_devops"),
        cloud_platform=CloudPlatform(cloud),
        stages=[PipelineStage(
            name="terraform_plan", purpose="provision infra",
            tools=list(tools), depends_on=[], optional=False, explanation="e",
        )],
        artifacts_strategy="a", security_strategy="s", approval_strategy="m",
        notifications=[], custom_requirement_addressed="",
    )


# --------------------------------------------------------------------------- #
# 1. Default sanitiser (allow_bicep=False) still forbids Bicep everywhere.
# --------------------------------------------------------------------------- #
class TestDefaultTerraformEverywhere:
    def test_bicep_still_rewritten_on_aws(self):
        p = _sanitize_iac(_plan(["bicep"], cloud="aws"))
        assert p.stages[0].tools == ["terraform"]

    def test_bicep_still_rewritten_on_gcp(self):
        p = _sanitize_iac(_plan(["bicep"], cloud="gcp"))
        assert p.stages[0].tools == ["terraform"]

    def test_bicep_still_rewritten_on_azure_when_flag_not_set(self):
        # Iteration-20 default: no opt-in => Bicep is still coerced.
        p = _sanitize_iac(_plan(["bicep"], cloud="azure"))
        assert p.stages[0].tools == ["terraform"]


# --------------------------------------------------------------------------- #
# 2. Opt-in sanitiser preserves Bicep but not other forbidden tools.
# --------------------------------------------------------------------------- #
class TestOptInBicep:
    def test_bicep_kept_when_allow_bicep_true(self):
        p = _sanitize_iac(_plan(["bicep"], cloud="azure"), allow_bicep=True)
        assert "bicep" in [t.lower() for t in p.stages[0].tools]
        assert "terraform" not in [t.lower() for t in p.stages[0].tools]

    def test_bicep_case_insensitive_kept(self):
        p = _sanitize_iac(_plan(["BICEP"], cloud="azure"), allow_bicep=True)
        # Original case is preserved.
        assert p.stages[0].tools == ["BICEP"]

    def test_bicep_kept_but_cloudformation_still_rewritten(self):
        p = _sanitize_iac(
            _plan(["bicep", "cloudformation", "az-cli"], cloud="azure"),
            allow_bicep=True,
        )
        tools_lower = [t.lower() for t in p.stages[0].tools]
        assert "bicep" in tools_lower
        assert "terraform" in tools_lower           # <- from CF rewrite
        assert "cloudformation" not in tools_lower
        assert "az-cli" in tools_lower              # legit helper preserved

    def test_pulumi_cdk_sam_all_rewritten_even_when_bicep_opt_in(self):
        p = _sanitize_iac(
            _plan(["Pulumi", "CDK", "sam"], cloud="azure"),
            allow_bicep=True,
        )
        # No bicep in this plan — only forbidden non-Bicep. Everything
        # collapses into a single `terraform` entry.
        assert p.stages[0].tools == ["terraform"]

    def test_custom_requirement_notes_opt_in(self):
        p = _sanitize_iac(_plan(["bicep"], cloud="azure"), allow_bicep=True)
        assert "Bicep opt-in was honoured" in (p.custom_requirement_addressed or "")


# --------------------------------------------------------------------------- #
# 3. PipelinePlanningAgent gating logic (unit test, no LLM).
# --------------------------------------------------------------------------- #
class TestPlannerAgentGating:
    def test_allow_bicep_only_when_azure_and_iac_tool_bicep(self):
        # We only exercise the gating logic — patch super().run() to avoid
        # calling the LLM. Inspect self._allow_bicep after run() completes.
        agent = PipelinePlanningAgent()

        captured = {}

        async def fake_super_run(self, **inputs):  # noqa: D401 - unbound
            captured["allow_bicep_during_super_run"] = agent._allow_bicep
            return _plan(["bicep"], cloud=inputs["cloud"].value)

        # Monkey-patch super().run() by replacing the bound method on the
        # BaseAgent parent for this instance only.
        from backend.agents.base import BaseAgent
        original = BaseAgent.run
        BaseAgent.run = fake_super_run  # type: ignore[assignment]
        try:
            import asyncio

            # 1) Azure + bicep => allow_bicep True
            asyncio.run(agent.run(
                analysis=None, tech=None, arch=None,
                ci=CIPlatform("azure_devops"),
                cloud=CloudPlatform("azure"),
                custom_requirement="",
                iac_tool="bicep",
            ))
            assert captured["allow_bicep_during_super_run"] is True

            # 2) AWS + bicep => must be False (Bicep is Azure-only).
            asyncio.run(agent.run(
                analysis=None, tech=None, arch=None,
                ci=CIPlatform("github_actions"),
                cloud=CloudPlatform("aws"),
                custom_requirement="",
                iac_tool="bicep",
            ))
            assert captured["allow_bicep_during_super_run"] is False

            # 3) Azure + default => False.
            asyncio.run(agent.run(
                analysis=None, tech=None, arch=None,
                ci=CIPlatform("azure_devops"),
                cloud=CloudPlatform("azure"),
                custom_requirement="",
                iac_tool="terraform",
            ))
            assert captured["allow_bicep_during_super_run"] is False
        finally:
            BaseAgent.run = original  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# 4. Frontend infra directive builder.
# --------------------------------------------------------------------------- #
class TestFrontendInfraDirective:
    def test_default_is_terraform_directive_on_all_clouds(self):
        from frontend.tabs.pipeline_generator import _build_infra_directive
        for cloud in ("aws", "azure", "gcp"):
            d = _build_infra_directive(cloud)
            assert "Terraform" in d or "terraform" in d
            # Even the Azure default must forbid Bicep.
            assert "Bicep" in d  # appears in the "do NOT use Bicep" line

    def test_bicep_opt_in_only_for_azure(self):
        from frontend.tabs.pipeline_generator import _build_infra_directive

        # AWS/GCP with iac_tool=bicep must be ignored (Bicep is Azure-only).
        aws_d = _build_infra_directive("aws", iac_tool="bicep")
        assert "Terraform" in aws_d or "terraform" in aws_d
        gcp_d = _build_infra_directive("gcp", iac_tool="bicep")
        assert "Terraform" in gcp_d or "terraform" in gcp_d

        # Azure + bicep flips the guidance.
        az_d = _build_infra_directive("azure", iac_tool="bicep")
        assert "Bicep" in az_d and "az deployment" in az_d
        assert "Do NOT emit Terraform" in az_d


# --------------------------------------------------------------------------- #
# 5. API surface exposes the new iac_tool field.
# --------------------------------------------------------------------------- #
class TestAPISurface:
    def test_generate_request_has_iac_tool_default_terraform(self):
        from backend.api.pipelines import GenerateRequest
        fields = GenerateRequest.model_fields
        assert "iac_tool" in fields
        # Pydantic v2 stores default on FieldInfo.default
        assert fields["iac_tool"].default == "terraform"

    def test_pipeline_service_generate_signature_accepts_iac_tool(self):
        from backend.services.pipeline_service import PipelineService
        sig = inspect.signature(PipelineService.generate)
        assert "iac_tool" in sig.parameters
        assert sig.parameters["iac_tool"].default == "terraform"

    def test_workflow_signature_accepts_iac_tool(self):
        from backend.orchestrator.workflows import run_pipeline_generation
        sig = inspect.signature(run_pipeline_generation)
        assert "iac_tool" in sig.parameters
        assert sig.parameters["iac_tool"].default == "terraform"
