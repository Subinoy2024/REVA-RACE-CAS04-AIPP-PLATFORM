"""Iteration-8 regression tests.

Covers the review request:
  - Frontend `pipeline_type` gr.Radio + _TYPE_DIRECTIVES + _generate signature.
  - Backend Pydantic accepts long custom_requirement values.
  - Minimal variables block in AzureDevOpsGenerator.render().
  - Planner SYSTEM prompt mentions Python-preferred scripts + "variables".
  - Cross-generator sanity: all 5 generators render with the minimal scenario.
"""

from __future__ import annotations

import inspect
import os
import re

import pytest
import requests
import yaml

from backend.agents.pipeline_planner import SYSTEM as PLANNER_SYSTEM
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
from frontend.tabs import pipeline_generator as pg_module

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


# ---------------------------------------------------------------------------
# Frontend module — pipeline_type radio + directive plumbing
# ---------------------------------------------------------------------------
class TestPipelineTypeFrontendModule:
    def test_type_directives_all_in_one_is_empty(self):
        assert pg_module._TYPE_DIRECTIVES["all_in_one"] == ""

    def test_type_directives_ci_contains_ci_only_and_no_deploy(self):
        ci_text = pg_module._TYPE_DIRECTIVES["ci"]
        assert "CI-ONLY" in ci_text
        assert re.search(r"no.*deploy|Do NOT include.*deploy", ci_text, re.IGNORECASE)

    def test_type_directives_cd_contains_cd_only(self):
        assert "CD-ONLY" in pg_module._TYPE_DIRECTIVES["cd"]

    def test_type_directives_infra_contains_infra_only_and_iac_tool(self):
        infra_text = pg_module._TYPE_DIRECTIVES["infra"]
        assert "INFRA-ONLY" in infra_text
        assert ("Terraform" in infra_text) or ("Bicep" in infra_text)

    def test_pipeline_types_option_list_has_expected_values(self):
        # Values (not labels) must include all scopes AIPP supports.
        values = [v for _label, v in pg_module.PIPELINE_TYPES]
        assert set(values) == {"all_in_one", "build_only", "ci", "cd", "infra"}

    def test_generate_signature_has_pipeline_type_and_agent_pool(self):
        sig = inspect.signature(pg_module._generate)
        params = list(sig.parameters)
        # Iteration-21: deployment_target sits between cloud and pipeline_type.
        # Expected order: repo_url, pat, branch, ci, cloud, deployment_target,
        #                 pipeline_type, agent_pool, iac_tool, custom_req
        assert params.index("deployment_target") == params.index("cloud") + 1
        assert params.index("pipeline_type") == params.index("deployment_target") + 1
        assert params.index("agent_pool") == params.index("pipeline_type") + 1
        assert params.index("iac_tool") == params.index("agent_pool") + 1
        assert params.index("custom_req") == params.index("iac_tool") + 1

    def test_build_tab_source_declares_gr_radio_for_pipeline_type(self):
        """A gr.Radio widget must be present so the user can pick pipeline_type."""
        src = inspect.getsource(pg_module.build_tab)
        assert "gr.Radio" in src, "build_tab must instantiate a gr.Radio for pipeline_type"
        # And the click wiring must include the radio in inputs
        assert "pipeline_type" in src, "build_tab must reference `pipeline_type` variable"

    def test_generate_prepends_type_directive_before_post(self, monkeypatch):
        """When pipeline_type != all_in_one, _generate must prepend the directive
        to custom_requirement before the SSE body is sent."""
        captured = {}

        def fake_sse(path, *, json_body, **kw):
            captured["path"] = path
            captured["json"] = json_body
            # Simulate one done event so the generator exits.
            yield {"kind": "result", "payload": {
                "pipeline": {"yaml_content": "stages: []", "filename": "x.yml"},
                "explanation": "", "plan": {}, "validation": {},
                "analysis": {"owner": "o", "name": "n"},
                "generation_seconds": 0.1,
            }}
            yield {"kind": "done"}

        monkeypatch.setattr(pg_module, "sse_post", fake_sse)

        list(pg_module._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "azure_devops", "azure", "unspecified", "ci", "", "terraform", "please skip Trivy",
        ))

        assert captured["path"] == "/api/pipelines/generate/stream"
        sent = captured["json"]["custom_requirement"]
        # The CI directive should appear BEFORE the user's own text.
        assert sent.startswith(pg_module._TYPE_DIRECTIVES["ci"])
        assert "please skip Trivy" in sent

    def test_generate_all_in_one_does_not_add_directive(self, monkeypatch):
        captured = {}

        def fake_sse(path, *, json_body, **kw):
            captured["json"] = json_body
            yield {"kind": "result", "payload": {
                "pipeline": {"yaml_content": "", "filename": "x.yml"},
                "explanation": "", "plan": {}, "validation": {},
                "analysis": {"owner": "o", "name": "n"},
                "generation_seconds": 0.0,
            }}
            yield {"kind": "done"}

        monkeypatch.setattr(pg_module, "sse_post", fake_sse)

        list(pg_module._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "azure_devops", "azure", "unspecified", "all_in_one", "", "terraform", "some custom text",
        ))
        sent = captured["json"]["custom_requirement"]
        # No CI/CD/INFRA marker leaked in.
        assert "PIPELINE TYPE:" not in sent
        assert sent.strip() == "some custom text"

    def test_build_tab_click_wiring_includes_pipeline_type(self):
        """The btn.click wiring must pass 10 inputs (deployment_target +
        pipeline_type + agent_pool + iac_tool + others) or the Generate
        button will raise TypeError at call time."""
        src = inspect.getsource(pg_module.build_tab)
        # Find the btn.click inputs list and count entries.
        m = re.search(
            r"btn\.click\(\s*_generate\s*,\s*inputs\s*=\s*\[([^\]]*)\]",
            src, re.DOTALL,
        )
        assert m, "Could not locate btn.click(_generate, inputs=[...]) wiring"
        inputs_list = [tok.strip() for tok in m.group(1).split(",") if tok.strip()]
        assert len(inputs_list) == 10, (
            f"btn.click wiring passes {len(inputs_list)} inputs, but _generate "
            f"needs 10. Current inputs: {inputs_list}"
        )
        assert "pipeline_type" in inputs_list, (
            "pipeline_type variable missing from btn.click(inputs=[...])"
        )
        assert "agent_pool" in inputs_list, (
            "agent_pool variable missing from btn.click(inputs=[...])"
        )
        assert "iac_tool" in inputs_list, (
            "iac_tool variable missing from btn.click(inputs=[...])"
        )
        assert "deployment_target" in inputs_list, (
            "deployment_target variable missing from btn.click(inputs=[...])"
        )


# ---------------------------------------------------------------------------
# Planner SYSTEM prompt
# ---------------------------------------------------------------------------
class TestPlannerSystemPromptUpdates:
    def test_prompt_mentions_python_for_helper_scripts(self):
        assert "Python" in PLANNER_SYSTEM
        # Contextual anchor — must be tied to scripts / snippet, not a
        # coincidental capitalisation of "Python" in unrelated text.
        assert re.search(r"Python.*(snippet|script)|(snippet|script).*Python",
                         PLANNER_SYSTEM, re.IGNORECASE | re.DOTALL)

    def test_prompt_mentions_variables_not_invented(self):
        # "variables" must appear in the prompt AND be tied to
        # a "do not invent" / "minimal" directive.
        assert "variables" in PLANNER_SYSTEM
        low = PLANNER_SYSTEM.lower()
        assert ("do not invent" in low) or ("minimal" in low) or ("did not ask" in low)


# ---------------------------------------------------------------------------
# Azure DevOps minimal variables block
# ---------------------------------------------------------------------------
def _make_tech(**over) -> TechnologyProfile:
    defaults = dict(
        language="python", framework="fastapi", package_manager="pip",
        build_tool="pip", test_framework="pytest",
        container_ready=True, kubernetes_ready=False, helm_ready=False,
    )
    defaults.update(over)
    return TechnologyProfile(**defaults)


def _make_plan(cloud="azure", ci="azure_devops") -> PipelinePlan:
    return PipelinePlan(
        ci_platform=CIPlatform(ci),
        cloud_platform=CloudPlatform(cloud),
        stages=[PipelineStage(name="build", purpose="p", tools=[], depends_on=[],
                              optional=False, explanation="e")],
        artifacts_strategy="a",
        security_strategy="s",
        approval_strategy="m",
        notifications=[],
        custom_requirement_addressed="",
    )


def _dev_only_env_plan() -> EnvironmentPlan:
    return EnvironmentPlan(rules=[EnvironmentRule(
        name=EnvironmentName("development"),
        trigger="develop_branch",
        requires_approval=False,
        health_check=True,
        smoke_test=True,
    )])


class TestAzureDevOpsMinimalVariables:
    """Exercises the vars_block branch in AzureDevOpsGenerator.render()."""

    def _render(self, cloud: str) -> dict:
        gen = AzureDevOpsGenerator(
            plan=_make_plan(cloud=cloud),
            tech=_make_tech(),
            env_plan=_dev_only_env_plan(),
            repo_name="demo",
        )
        return yaml.safe_load(gen.render())

    def test_variables_block_contains_only_literals_no_cyclical_refs(self):
        """Iteration 15 regression: the `variables:` block MUST NOT contain
        self-referencing entries like `REGISTRY_NAME: $(REGISTRY_NAME)` —
        those cause ADO to warn 'cyclical reference was detected' and refuse
        to expand the variable at runtime. User-provided variables must be
        supplied at the pipeline level (or via a variable group), not here."""
        doc = self._render("azure")
        vars_block = doc["variables"]
        # Only these literal, non-cyclical entries are allowed:
        assert set(vars_block.keys()).issubset({"IMAGE_NAME", "TAG"}), (
            f"variables block leaked user-provided keys: {list(vars_block.keys())}"
        )
        # And nothing in the values should reference itself.
        for k, v in vars_block.items():
            if isinstance(v, str):
                assert f"$({k})" not in v, (
                    f"CYCLICAL reference: {k}={v!r} contains $({k})"
                )

    def test_minimal_variables_when_required_env_is_empty(self, monkeypatch):
        """Force target.required_env=[] via monkeypatch. The variables block
        must be the minimal 2-key literal block (IMAGE_NAME + TAG)."""
        from backend.generators import azure_devops as ado_mod
        from backend.generators import deploy_targets as dt_mod

        # Build a stand-in target with an empty required_env list.
        real_target = dt_mod.AZURE_APP_SERVICE
        stub_target = dt_mod.DeployTarget(
            id=real_target.id,
            display=real_target.display,
            cloud=real_target.cloud,
            kind=real_target.kind,
            commands=real_target.commands,
            required_env=[],           # <-- forced empty
            notes=real_target.notes,
        )
        monkeypatch.setattr(ado_mod, "pick_deploy_target",
                            lambda **_: stub_target)

        gen = AzureDevOpsGenerator(
            plan=_make_plan(cloud="azure"),
            tech=_make_tech(),
            env_plan=_dev_only_env_plan(),
            repo_name="demo",
        )
        doc = yaml.safe_load(gen.render())
        assert set(doc["variables"].keys()) == {"IMAGE_NAME", "TAG"}, (
            f"Expected minimal 2-var block, got {list(doc['variables'].keys())}"
        )

    def test_minimal_case_has_no_placeholder_wall(self, monkeypatch):
        from backend.generators import azure_devops as ado_mod
        from backend.generators import deploy_targets as dt_mod

        real_target = dt_mod.AZURE_APP_SERVICE
        stub_target = dt_mod.DeployTarget(
            id=real_target.id, display=real_target.display,
            cloud=real_target.cloud, kind=real_target.kind,
            commands=real_target.commands, required_env=[],
            notes=real_target.notes,
        )
        monkeypatch.setattr(ado_mod, "pick_deploy_target",
                            lambda **_: stub_target)

        gen = AzureDevOpsGenerator(
            plan=_make_plan(cloud="azure"),
            tech=_make_tech(),
            env_plan=_dev_only_env_plan(),
            repo_name="demo",
        )
        doc = yaml.safe_load(gen.render())
        placeholder_count = sum(
            1 for v in doc["variables"].values()
            if isinstance(v, str) and v.startswith("$(") and v.endswith(")")
        )
        # Only TAG (=$(Build.SourceVersion)) is $(...) in the minimal case.
        assert placeholder_count <= 1


# ---------------------------------------------------------------------------
# Backend API — accepts long custom_requirement (no 422)
# ---------------------------------------------------------------------------
class TestPipelinesGenerateAcceptsLongCustomRequirement:
    def test_long_ci_only_directive_is_not_422(self):
        long_req = (
            pg_module._TYPE_DIRECTIVES["ci"]
            + "\n\nAlso, please skip Trivy and use pnpm install."
        )
        payload = {
            "repo_url": "https://github.com/aipp-demo/nonexistent-repo",
            "github_pat": "ghp_bogus_but_syntactically_valid_1234567890",
            "branch": "main",
            "ci_platform": "azure_devops",
            "cloud_platform": "azure",
            "custom_requirement": long_req,
        }
        try:
            r = requests.post(f"{BASE_URL}/api/pipelines/generate",
                              json=payload, timeout=30)
        except requests.RequestException as e:
            pytest.skip(f"backend unreachable: {e}")
        # LLM/repo will realistically fail (sk-test key, fake repo),
        # so we expect 4xx or 5xx — but NEVER a Pydantic 422 validation error.
        assert r.status_code != 422, (
            f"Pydantic rejected long custom_requirement: {r.text}"
        )


# ---------------------------------------------------------------------------
# Cross-generator sanity — all 5 render with minimal scenario
# ---------------------------------------------------------------------------
class TestCrossGeneratorMinimalScenario:
    @pytest.mark.parametrize("cls, ci_name", [
        (AzureDevOpsGenerator, "azure_devops"),
        (GitHubActionsGenerator, "github_actions"),
        (GitLabCIGenerator, "gitlab_ci"),
        (HarnessGenerator, "harness"),
        (TektonGenerator, "tekton"),
    ])
    def test_generator_renders_with_minimal_scenario(self, cls, ci_name):
        gen = cls(
            plan=_make_plan(cloud="azure", ci=ci_name),
            tech=_make_tech(),
            env_plan=_dev_only_env_plan(),
            repo_name="demo",
        )
        text = gen.render()
        assert isinstance(text, str) and len(text) > 100, (
            f"{cls.__name__} produced empty/short YAML"
        )
