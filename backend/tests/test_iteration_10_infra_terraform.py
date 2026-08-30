"""Iteration-10 regression tests — AWS + Infra must yield Terraform, never Bicep.

Bug reported by the user:
  Selecting `cloud=aws` and `pipeline_type=infra` incorrectly produced a
  plan containing Azure Bicep steps. AWS does not support Bicep — the
  planner is now hard-locked to Terraform for ALL clouds.

Covers:
  1. Frontend `_TYPE_DIRECTIVES["infra"]` is strict Terraform-only and lists
     Bicep as a forbidden tool.
  2. `_build_infra_directive(cloud)` appends the correct provider hint per
     cloud (aws → hashicorp/aws, azure → hashicorp/azurerm, gcp → hashicorp/google).
  3. Planner SYSTEM prompt contains the strict IaC rule.
  4. Backend `_sanitize_iac()` post-processor rewrites Bicep / CloudFormation
     / CDK / SAM / Pulumi / Deployment Manager to `terraform`.
  5. When `pipeline_type=infra` is chosen, `_generate` prepends the
     cloud-specific Terraform directive (not the raw shared string).
"""

from __future__ import annotations

from backend.agents.pipeline_planner import (
    SYSTEM as PLANNER_SYSTEM,
    _sanitize_iac,
    _FORBIDDEN_IAC_TOOLS,
)
from backend.models.pipeline import (
    CIPlatform,
    CloudPlatform,
    PipelinePlan,
    PipelineStage,
)
from frontend.tabs import pipeline_generator as pg


# ---------------------------------------------------------------------------
# Frontend directive
# ---------------------------------------------------------------------------
class TestInfraDirectiveIsTerraformOnly:
    def test_infra_directive_names_terraform_stages(self):
        text = pg._TYPE_DIRECTIVES["infra"]
        for step in ["terraform init", "terraform plan", "terraform apply"]:
            assert step in text, f"infra directive missing `{step}`"

    def test_infra_directive_forbids_bicep_and_other_iacs(self):
        text = pg._TYPE_DIRECTIVES["infra"]
        # Every forbidden IaC must be explicitly denied in the LLM directive.
        for forbidden in ["Bicep", "ARM", "CloudFormation",
                          "CDK", "SAM", "Pulumi"]:
            assert forbidden in text, (
                f"infra directive does not warn against `{forbidden}`"
            )

    def test_infra_directive_says_never_or_must_not(self):
        text = pg._TYPE_DIRECTIVES["infra"].lower()
        assert "must not" in text or "never" in text

    def test_pipeline_types_label_no_longer_mentions_bicep(self):
        # Label should read "Terraform" only — no "Bicep" leak in the UI.
        labels = [lbl for lbl, _val in pg.PIPELINE_TYPES]
        infra_label = [lbl for lbl in labels if "Infra" in lbl][0]
        assert "Bicep" not in infra_label
        assert "Terraform" in infra_label

    def test_radio_info_no_longer_mentions_bicep(self):
        # The gr.Radio `info=` string in build_tab must not RECOMMEND Bicep.
        # Iteration-20: Bicep is now exposed only as an explicit opt-in
        # dropdown label ("Bicep (Azure only, opt-in)"). The pipeline-scope
        # Radio info must still stay Terraform-only.
        import inspect
        src = inspect.getsource(pg.build_tab)
        # Locate the Radio(info=...) string.
        # Radio is created for pipeline_type — its `info=` must not mention Bicep.
        radio_block_start = src.find("pipeline_type = gr.Radio(")
        assert radio_block_start != -1
        radio_block_end = src.find(")", radio_block_start)
        radio_src = src[radio_block_start:radio_block_end]
        assert "Bicep" not in radio_src, (
            "pipeline_type Radio still mentions Bicep — the scope hint must "
            "be Terraform-only."
        )


# ---------------------------------------------------------------------------
# Cloud-specific infra directive builder
# ---------------------------------------------------------------------------
class TestBuildInfraDirectivePerCloud:
    def test_aws_uses_hashicorp_aws_and_s3_backend(self):
        d = pg._build_infra_directive("aws")
        assert "hashicorp/aws" in d
        assert "S3" in d and "DynamoDB" in d
        # No Azure / GCP leakage.
        assert "azurerm" not in d
        assert "hashicorp/google" not in d

    def test_azure_uses_azurerm(self):
        d = pg._build_infra_directive("azure")
        assert "hashicorp/azurerm" in d
        # Even for Azure, Bicep must be explicitly denied.
        assert "Bicep" in d

    def test_gcp_uses_hashicorp_google(self):
        d = pg._build_infra_directive("gcp")
        assert "hashicorp/google" in d
        assert "GCS" in d

    def test_unknown_cloud_still_returns_base_directive(self):
        d = pg._build_infra_directive("does-not-exist")
        # Base terraform commands still emitted.
        assert "terraform init" in d
        assert "terraform apply" in d


# ---------------------------------------------------------------------------
# _generate() wires the cloud-specific directive on pipeline_type=infra
# ---------------------------------------------------------------------------
class TestGenerateAppliesCloudSpecificInfraDirective:
    def _fake_sse_capture(self, captured):
        def _fp(path, *, json_body, **kw):
            captured["path"] = path
            captured["json"] = json_body
            yield {"kind": "result", "payload": {
                "pipeline": {"yaml_content": "stages: []", "filename": "x.yml"},
                "explanation": "", "plan": {}, "validation": {},
                "analysis": {"owner": "o", "name": "n"},
                "generation_seconds": 0.0,
            }}
            yield {"kind": "done"}
        return _fp

    def test_infra_aws_prepends_hashicorp_aws_hint(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(pg, "sse_post", self._fake_sse_capture(captured))
        list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "github_actions", "aws", "unspecified", "infra", "", "terraform", "",
        ))
        sent = captured["json"]["custom_requirement"]
        assert "hashicorp/aws" in sent
        assert "S3" in sent  # backend hint
        # Bicep must be listed as forbidden, never as a candidate.
        assert "MUST NOT emit Bicep" in sent or "NOT use" in sent

    def test_infra_azure_prepends_azurerm_hint(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(pg, "sse_post", self._fake_sse_capture(captured))
        list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "github_actions", "azure", "unspecified", "infra", "", "terraform", "",
        ))
        sent = captured["json"]["custom_requirement"]
        assert "hashicorp/azurerm" in sent
        # Azure infra must still forbid Bicep — unified Terraform.
        assert "Bicep" in sent  # only appears in "do NOT use Bicep" text

    def test_infra_gcp_prepends_hashicorp_google_hint(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(pg, "sse_post", self._fake_sse_capture(captured))
        list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "github_actions", "gcp", "unspecified", "infra", "", "terraform", "",
        ))
        sent = captured["json"]["custom_requirement"]
        assert "hashicorp/google" in sent


# ---------------------------------------------------------------------------
# Planner SYSTEM prompt — strict IaC rule
# ---------------------------------------------------------------------------
class TestPlannerSystemPromptHasStrictIaCRule:
    def test_prompt_mandates_terraform(self):
        assert "Terraform" in PLANNER_SYSTEM
        # Contextual anchor — tied to IaC / infra, not a coincidental mention.
        low = PLANNER_SYSTEM.lower()
        assert "infrastructure-as-code" in low or "iac" in low

    def test_prompt_forbids_bicep_and_variants(self):
        for forbidden in ["Bicep", "CloudFormation", "CDK", "SAM", "Pulumi"]:
            assert forbidden in PLANNER_SYSTEM, (
                f"planner SYSTEM does not forbid `{forbidden}`"
            )

    def test_prompt_says_never_or_must_not(self):
        assert ("NEVER" in PLANNER_SYSTEM) or ("MUST NOT" in PLANNER_SYSTEM)


# ---------------------------------------------------------------------------
# Post-processor: forbidden IaC tools are rewritten to `terraform`
# ---------------------------------------------------------------------------
def _make_plan(tools, cloud="aws", stage_name="terraform_plan",
               purpose="plan infra") -> PipelinePlan:
    return PipelinePlan(
        ci_platform=CIPlatform("github_actions"),
        cloud_platform=CloudPlatform(cloud),
        stages=[PipelineStage(
            name=stage_name, purpose=purpose, tools=list(tools),
            depends_on=[], optional=False, explanation="e",
        )],
        artifacts_strategy="a", security_strategy="s", approval_strategy="m",
        notifications=[], custom_requirement_addressed="",
    )


class TestSanitizeIACPostProcessor:
    def test_bicep_is_rewritten_to_terraform(self):
        plan = _make_plan(tools=["bicep"], cloud="aws")
        out = _sanitize_iac(plan)
        assert out.stages[0].tools == ["terraform"]
        assert "AIPP note" in out.stages[0].explanation

    def test_cloudformation_is_rewritten_to_terraform(self):
        plan = _make_plan(tools=["cloudformation", "aws-cli"], cloud="aws")
        out = _sanitize_iac(plan)
        assert "terraform" in out.stages[0].tools
        # aws-cli is a legit helper — must survive.
        assert "aws-cli" in out.stages[0].tools
        assert not any(
            t.lower() in _FORBIDDEN_IAC_TOOLS for t in out.stages[0].tools
        )

    def test_pulumi_and_cdk_and_sam_all_swapped(self):
        plan = _make_plan(tools=["Pulumi", "CDK", "sam"], cloud="aws")
        out = _sanitize_iac(plan)
        assert out.stages[0].tools == ["terraform"]

    def test_terraform_only_plan_is_untouched(self):
        plan = _make_plan(tools=["terraform", "tflint"], cloud="azure")
        out = _sanitize_iac(plan)
        assert out.stages[0].tools == ["terraform", "tflint"]
        assert "AIPP note" not in (out.stages[0].explanation or "")

    def test_non_iac_stage_with_matching_word_untouched(self):
        # A "build" stage that happens to use npm must NOT be touched.
        plan = _make_plan(tools=["npm"], cloud="aws",
                          stage_name="build", purpose="compile app")
        out = _sanitize_iac(plan)
        assert out.stages[0].tools == ["npm"]

    def test_custom_requirement_addressed_gets_coercion_note(self):
        plan = _make_plan(tools=["bicep"], cloud="aws")
        plan.custom_requirement_addressed = "user asked X"
        out = _sanitize_iac(plan)
        assert "AIPP coerced" in out.custom_requirement_addressed

    def test_case_insensitive_and_dashed_variants_are_matched(self):
        plan = _make_plan(tools=["BICEP", "AWS-CDK", "arm-template"], cloud="aws")
        out = _sanitize_iac(plan)
        # All 3 forbidden entries should collapse to one `terraform`.
        assert out.stages[0].tools == ["terraform"]
