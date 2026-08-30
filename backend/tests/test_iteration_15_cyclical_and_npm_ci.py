"""Iteration-15 regression tests — cyclical variable refs + npm ci resilience.

Bugs reported by the user's ADO run log:

  A. "Unable to expand variable 'REGISTRY_NAME'. A cyclical reference was
     detected." (also for AZURE_TENANT_ID, AZURE_CLIENT_ID, IMAGE, AZURE_RG,
     AZURE_CLIENT_SECRET, AZURE_WEBAPP_NAME, ACR_NAME)

     Root cause: `variables: { REGISTRY_NAME: $(REGISTRY_NAME) }` is a
     self-reference. ADO detects the cycle and refuses to expand it.

  B. npm ci failed with EUSAGE:
        "npm ci can only install packages when your package.json and
         package-lock.json ... are in sync."

     Root cause: `install=["npm ci"]` is too strict for real-world repos
     that get scaffolded / regenerated frequently.

Fix:
  A. Remove ALL user-provided variables from the `variables:` block. Only
     literals (IMAGE_NAME + TAG) remain. The user supplies REGISTRY_NAME,
     AZURE_WEBAPP_NAME etc. as pipeline variables — ADO resolves those
     natively at runtime.
  B. Node install commands now fall back to `npm install` / `yarn install`
     / `pnpm install` when the lock file is out of sync.
"""

from __future__ import annotations

import yaml as _yaml

from backend.generators import azure_devops as ado_mod
from backend.generators import commands as cmd_mod
from backend.generators import deploy_targets as dt_mod
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


def _mk_gen(*, cloud: str = "azure", scope: str = "all_in_one",
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


# ---------------------------------------------------------------------------
# Bug A — no cyclical variable references
# ---------------------------------------------------------------------------
class TestNoCyclicalVariableReferences:
    def _self_ref_keys(self, vars_block: dict) -> list:
        """Keys whose value contains a runtime reference to themselves."""
        out = []
        for k, v in vars_block.items():
            if isinstance(v, str) and f"$({k})" in v:
                out.append(k)
        return out

    def test_azure_all_in_one_variables_block_has_no_self_references(self):
        doc = _yaml.safe_load(_mk_gen(cloud="azure", scope="all_in_one").render())
        vars_block = doc.get("variables", {})
        assert self._self_ref_keys(vars_block) == [], (
            f"CYCLICAL vars: {self._self_ref_keys(vars_block)} in {vars_block}"
        )

    def test_aws_variables_block_has_no_self_references(self):
        doc = _yaml.safe_load(_mk_gen(cloud="aws").render())
        assert self._self_ref_keys(doc.get("variables", {})) == []

    def test_gcp_variables_block_has_no_self_references(self):
        doc = _yaml.safe_load(_mk_gen(cloud="gcp").render())
        assert self._self_ref_keys(doc.get("variables", {})) == []

    def test_variables_block_keys_are_only_literals(self):
        """Only literal, generator-owned keys are allowed in the block.
        Anything the user supplies (REGISTRY_NAME, AZURE_WEBAPP_NAME, etc.)
        must be provided at the pipeline level, not redeclared here."""
        doc = _yaml.safe_load(_mk_gen(cloud="azure").render())
        allowed = {"IMAGE_NAME", "TAG"}
        got = set(doc.get("variables", {}).keys())
        assert got.issubset(allowed), (
            f"variables block leaked user-provided keys {got - allowed}; "
            f"those must come from pipeline variables / variable groups instead."
        )

    def test_removed_specific_user_keys(self):
        """The specific keys the user's ADO log flagged as cyclical must
        NOT appear in the emitted variables block."""
        yml = _mk_gen(cloud="azure").render()
        doc = _yaml.safe_load(yml)
        offenders = ["REGISTRY_NAME", "AZURE_TENANT_ID", "AZURE_CLIENT_ID",
                     "AZURE_CLIENT_SECRET", "AZURE_WEBAPP_NAME", "AZURE_RG",
                     "ACR_NAME", "IMAGE"]
        for k in offenders:
            assert k not in doc.get("variables", {}), (
                f"variables block still contains {k} — remove it to avoid "
                f"'cyclical reference was detected' warnings in ADO"
            )

    def test_docker_push_step_still_references_registry_and_image(self):
        """The build/push steps must still USE $(REGISTRY_NAME) / $(IMAGE_NAME)
        at runtime — ADO resolves them from pipeline vars, not our block."""
        yml = _mk_gen(cloud="azure", scope="all_in_one").render()
        assert "$(REGISTRY_NAME).azurecr.io" in yml
        assert "$(IMAGE_NAME):$(TAG)" in yml
        assert "docker push $(REGISTRY_NAME).azurecr.io/$(IMAGE_NAME):$(TAG)" in yml


# ---------------------------------------------------------------------------
# Bug B — npm ci resilience to out-of-sync lockfiles
# ---------------------------------------------------------------------------
class TestNodeInstallCommandsAreResilient:
    def test_npm_install_falls_back_when_lockfile_out_of_sync(self):
        assert cmd_mod.NODE_NPM.install == [
            "npm ci || npm install --no-audit --no-fund"
        ], (
            f"NODE_NPM install should be resilient — got "
            f"{cmd_mod.NODE_NPM.install}"
        )

    def test_yarn_install_falls_back(self):
        assert cmd_mod.NODE_YARN.install == [
            "yarn install --frozen-lockfile || yarn install"
        ]

    def test_pnpm_install_falls_back(self):
        assert cmd_mod.NODE_PNPM.install == [
            "pnpm install --frozen-lockfile || pnpm install"
        ]

    def test_install_command_still_starts_with_strict_variant(self):
        """We want the fast/strict variant to run FIRST (deterministic
        install when the lock file is in sync). Fallback only kicks in when
        the strict variant exits non-zero."""
        for lang in [cmd_mod.NODE_NPM, cmd_mod.NODE_YARN, cmd_mod.NODE_PNPM]:
            cmd = lang.install[0]
            assert cmd.split(" ||")[0].strip() in {
                "npm ci", "yarn install --frozen-lockfile",
                "pnpm install --frozen-lockfile",
            }


# ---------------------------------------------------------------------------
# End-to-end YAML sanity — validates the fix landed on a real render
# ---------------------------------------------------------------------------
class TestRenderedYAMLIsCyclicalFree:
    def test_full_yaml_can_be_re_parsed_and_variables_is_dict(self):
        yml = _mk_gen(cloud="azure").render()
        doc = _yaml.safe_load(yml)
        assert isinstance(doc.get("variables"), dict)

    def test_no_line_contains_a_self_referencing_variable_binding(self):
        """Sweep every `KEY: $(KEY)` pattern in the raw YAML."""
        import re
        yml = _mk_gen(cloud="azure").render()
        pattern = re.compile(r"^\s*(\w+)\s*:\s*\$\(\1\)\s*$", re.MULTILINE)
        matches = pattern.findall(yml)
        assert matches == [], (
            f"Self-referencing lines still present: {matches}"
        )
