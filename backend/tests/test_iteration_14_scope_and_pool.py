"""Iteration-14 regression tests — pipeline_type now flows into the YAML
generator (not just the LLM planner), and users can pick a self-hosted
agent pool.

Bug reported by the user (self-hosted agent, CI-only):
  "I am not deploying anything ... it should build as it ci ... why does it
   need connection with Azure"

Root cause: `pipeline_type=ci` was only prepended to the LLM prompt. The
deterministic YAML generator always emitted build + security + package +
deploy stages regardless, forcing an Azure SC even for pure CI.

Fix (this iteration):
  1. `pipeline_type` + `agent_pool` are new fields on GenerateRequest.
  2. State + orchestrator forward them to the generator.
  3. Azure DevOps generator branches on `pipeline_type`:
       - `build_only`  → build + security only (no push, no SC needed)
       - `ci`          → build + security + package (push to registry)
       - `cd`          → package + deploy_* only
       - `infra`       → one Terraform stage
       - `all_in_one`  → previous behaviour
  4. `agent_pool` sets `pool: {name: <pool>}` for self-hosted agents;
     unset falls back to Microsoft-hosted `vmImage: ubuntu-22.04`.
  5. UI has a new "Build & Test only" radio option and an "Agent pool"
     text field.
"""

from __future__ import annotations

import inspect

import yaml as _yaml

from backend.api.pipelines import GenerateRequest
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
from frontend.tabs import pipeline_generator as pg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _mk_gen(*, scope: str, cloud: str = "azure",
            pool: str | None = None) -> AzureDevOpsGenerator:
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
        plan=plan, env_plan=env, tech=tech, repo_name="medico-bloom",
        pipeline_type=scope, agent_pool=pool,
    )


def _stages(scope: str, cloud: str = "azure", pool: str | None = None):
    doc = _yaml.safe_load(_mk_gen(scope=scope, cloud=cloud, pool=pool).render())
    return [s.get("stage") for s in doc["stages"]]


# ---------------------------------------------------------------------------
# 1. API layer accepts new fields
# ---------------------------------------------------------------------------
class TestGenerateRequestNewFields:
    def test_pipeline_type_field_exists_with_default(self):
        req = GenerateRequest(
            repo_url="https://github.com/o/n", github_pat="ghp_abcdefgh",
            ci_platform="github_actions", cloud_platform="aws",
        )
        assert req.pipeline_type == "all_in_one"
        assert req.agent_pool is None

    def test_pipeline_type_accepts_build_only(self):
        req = GenerateRequest(
            repo_url="https://github.com/o/n", github_pat="ghp_abcdefgh",
            ci_platform="github_actions", cloud_platform="aws",
            pipeline_type="build_only", agent_pool="default",
        )
        assert req.pipeline_type == "build_only"
        assert req.agent_pool == "default"


# ---------------------------------------------------------------------------
# 2. Pipeline-scope stages emitted correctly
# ---------------------------------------------------------------------------
class TestScopeToStagesMapping:
    def test_all_in_one_has_build_security_package_deploys(self):
        stages = _stages("all_in_one")
        assert "build" in stages
        assert "security" in stages
        assert "package" in stages
        assert any(s.startswith("deploy_") for s in stages)

    def test_ci_has_no_deploy_stages(self):
        stages = _stages("ci")
        assert "build" in stages
        assert "package" in stages     # CI still pushes container to ACR
        assert not any(s.startswith("deploy_") for s in stages)

    def test_build_only_has_no_package_and_no_deploy(self):
        stages = _stages("build_only")
        assert stages == ["build", "security"]

    def test_cd_only_has_no_build_or_security(self):
        stages = _stages("cd")
        assert "build" not in stages
        assert "security" not in stages
        assert "package" in stages
        assert any(s.startswith("deploy_") for s in stages)

    def test_infra_has_production_terraform_stages(self):
        # Iteration 17 upgraded the infra pipeline from a single lightweight
        # stage to a 4-stage production flow (validate + plan + policy + apply).
        stages = _stages("infra")
        assert stages == [
            "terraform_validate",
            "terraform_plan",
            "terraform_policy",
            "terraform_apply",
        ]


# ---------------------------------------------------------------------------
# 3. build_only never emits an Azure SC parameter (fixes user's blocker)
# ---------------------------------------------------------------------------
class TestBuildOnlyNoAzureSCRequired:
    def test_build_only_azure_yaml_has_no_parameters_block(self):
        yml = _mk_gen(scope="build_only", cloud="azure").render()
        doc = _yaml.safe_load(yml)
        # No SC needed → no `parameters:` block emitted at all.
        assert "parameters" not in doc, (
            f"build_only must not emit a parameters block, got {doc.get('parameters')}"
        )

    def test_build_only_yaml_has_no_azureSubscription_field(self):
        yml = _mk_gen(scope="build_only", cloud="azure").render()
        assert "azureSubscription" not in yml
        assert "awsCredentials" not in yml
        assert "connectedServiceNameARM" not in yml

    def test_build_only_yaml_has_no_docker_push_step(self):
        yml = _mk_gen(scope="build_only", cloud="azure").render()
        assert "docker push" not in yml
        assert "docker buildx" not in yml

    def test_build_only_yaml_still_has_tests_and_scans(self):
        yml = _mk_gen(scope="build_only", cloud="azure").render()
        # unit test + security scan steps must still run — this is the
        # whole point of "Build & Test only".
        assert "unit test" in yml.lower()
        assert "SAST" in yml or "sast" in yml.lower()


# ---------------------------------------------------------------------------
# 4. Agent pool: self-hosted vs Microsoft-hosted
# ---------------------------------------------------------------------------
class TestAgentPoolBlock:
    def test_default_pool_is_microsoft_hosted_ubuntu(self):
        doc = _yaml.safe_load(_mk_gen(scope="ci").render())
        assert doc["pool"] == {"vmImage": "ubuntu-22.04"}

    def test_named_pool_switches_to_self_hosted(self):
        doc = _yaml.safe_load(_mk_gen(scope="ci", pool="default").render())
        assert doc["pool"] == {"name": "default"}

    def test_empty_string_pool_falls_back_to_default(self):
        doc = _yaml.safe_load(_mk_gen(scope="ci", pool="   ").render())
        assert doc["pool"] == {"vmImage": "ubuntu-22.04"}

    def test_custom_named_pool_is_preserved(self):
        doc = _yaml.safe_load(_mk_gen(scope="ci", pool="AIPP-Agents").render())
        assert doc["pool"] == {"name": "AIPP-Agents"}


# ---------------------------------------------------------------------------
# 5. Infra stage uses real Terraform commands
# ---------------------------------------------------------------------------
class TestInfraStageEmitsRealTerraformCommands:
    def test_terraform_stage_has_init_plan_apply(self):
        yml = _mk_gen(scope="infra", cloud="aws").render()
        for cmd in ["terraform init", "terraform validate",
                    "terraform plan", "terraform apply"]:
            assert cmd in yml, f"infra stage missing `{cmd}`"

    def test_terraform_stage_display_name_names_provider(self):
        yml = _mk_gen(scope="infra", cloud="aws").render()
        assert "hashicorp/aws" in yml
        yml_az = _mk_gen(scope="infra", cloud="azure").render()
        assert "hashicorp/azurerm" in yml_az
        yml_gcp = _mk_gen(scope="infra", cloud="gcp").render()
        assert "hashicorp/google" in yml_gcp


# ---------------------------------------------------------------------------
# 6. UI: PIPELINE_TYPES exposes build_only and agent_pool field exists
# ---------------------------------------------------------------------------
class TestUIExposesNewOptions:
    def test_pipeline_types_lists_build_only(self):
        values = [v for _lbl, v in pg.PIPELINE_TYPES]
        assert "build_only" in values
        # build_only should come BEFORE ci (safer default, visually first)
        assert values.index("build_only") < values.index("ci")

    def test_build_tab_source_declares_agent_pool_textbox(self):
        src = inspect.getsource(pg.build_tab)
        assert "pg-agent-pool" in src, (
            "build_tab must declare a gr.Textbox for agent_pool with "
            "elem_id 'pg-agent-pool'"
        )
        assert "agent_pool" in src

    def test_generate_signature_has_agent_pool(self):
        params = list(inspect.signature(pg._generate).parameters)
        assert "agent_pool" in params
        # Order: ..., pipeline_type, agent_pool, custom_req
        assert params.index("agent_pool") == params.index("pipeline_type") + 1

    def test_generate_sends_pipeline_type_and_agent_pool_in_body(self, monkeypatch):
        captured = {}

        def fake_sse(path, *, json_body, **_kw):
            captured["json"] = json_body
            yield {"kind": "result", "payload": {
                "pipeline": {"yaml_content": "", "filename": "x.yml"},
                "explanation": "", "plan": {}, "validation": {},
                "analysis": {"owner": "o", "name": "n"},
                "generation_seconds": 0.0,
            }}
            yield {"kind": "done"}

        monkeypatch.setattr(pg, "sse_post", fake_sse)
        list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "azure_devops", "azure", "unspecified", "build_only", "default", "terraform", "",
        ))
        assert captured["json"]["pipeline_type"] == "build_only"
        assert captured["json"]["agent_pool"] == "default"

    def test_generate_sends_none_agent_pool_when_field_empty(self, monkeypatch):
        captured = {}

        def fake_sse(path, *, json_body, **_kw):
            captured["json"] = json_body
            yield {"kind": "result", "payload": {
                "pipeline": {"yaml_content": "", "filename": "x.yml"},
                "explanation": "", "plan": {}, "validation": {},
                "analysis": {"owner": "o", "name": "n"},
                "generation_seconds": 0.0,
            }}
            yield {"kind": "done"}

        monkeypatch.setattr(pg, "sse_post", fake_sse)
        list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "azure_devops", "azure", "unspecified", "ci", "", "terraform", "",
        ))
        assert captured["json"]["agent_pool"] is None


# ---------------------------------------------------------------------------
# 7. build_only setup instructions mention self-hosted + no SC needed
# ---------------------------------------------------------------------------
class TestBuildOnlySetupInstructions:
    def test_build_only_setup_says_no_service_connection_needed(self):
        md = pg._setup_instructions("azure_devops", "main", "build_only")
        assert "Build & Test only" in md or "safest" in md
        assert "no service connections" in md.lower()
        assert "self-hosted" in md.lower()
