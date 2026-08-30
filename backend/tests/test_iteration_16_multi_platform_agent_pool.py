"""Iteration-16 regression tests — three user-reported concerns:

1. Test command was hardcoded as `npm test -- --ci` which is a Jest-only flag.
   Vitest rejects `--ci` at parse time ("Unknown option `--ci`"). Fix: drop
   the framework-specific flag — the repo's own `package.json.scripts.test`
   already knows how to test itself; `--if-present` lets us skip cleanly if
   there is no test script at all.

2. Test framework detection should come from the repo (which the LLM
   technology agent already inspects), not from hardcoded generator flags.

3. `agent_pool` was labelled "Azure DevOps only" but should apply to every
   CI platform. Wired it through the two other widely-used ones — GitHub
   Actions (`runs-on: [self-hosted, <label>]`) and GitLab CI
   (`tags: [<label>]` per job).
"""

from __future__ import annotations

import inspect

import yaml as _yaml

from backend.generators import commands as cmd_mod
from backend.generators.github_actions import GitHubActionsGenerator
from backend.generators.gitlab_ci import GitLabCIGenerator
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


def _mk_kwargs(ci_platform, cloud="azure", pool=None):
    plan = PipelinePlan(
        ci_platform=CIPlatform(ci_platform), cloud_platform=CloudPlatform(cloud),
        stages=[], artifacts_strategy="acr", security_strategy="trivy",
        approval_strategy="manual", notifications=[], custom_requirement_addressed="",
    )
    env = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch"),
        EnvironmentRule(name=EnvironmentName.production, trigger="version_tag",
                        requires_approval=True),
    ])
    tech = TechnologyProfile(
        language="javascript", framework="react", package_manager="npm",
        containerized=True, kubernetes_ready=False, test_frameworks=["vitest"],
        build_tools=[], notes=[],
    )
    return dict(plan=plan, env_plan=env, tech=tech, repo_name="medico-bloom",
                pipeline_type="all_in_one", agent_pool=pool)


# ---------------------------------------------------------------------------
# 1. No hardcoded --ci flag in test commands
# ---------------------------------------------------------------------------
class TestNoJestOnlyCIFlag:
    def test_npm_test_command_has_no_ci_flag(self):
        cmds = cmd_mod.NODE_NPM.unit_test
        for cmd in cmds:
            assert " --ci" not in cmd, (
                f"NODE_NPM test command still contains Jest-only `--ci` "
                f"flag: {cmd!r} (breaks vitest / mocha)"
            )

    def test_yarn_test_command_has_no_ci_flag(self):
        for cmd in cmd_mod.NODE_YARN.unit_test:
            assert " --ci" not in cmd
            assert "--ci" not in cmd.split()

    def test_pnpm_test_command_has_no_ci_flag(self):
        for cmd in cmd_mod.NODE_PNPM.unit_test:
            assert " --ci" not in cmd
            assert "--ci" not in cmd.split()

    def test_test_command_relies_on_package_json_script(self):
        """The test invocation must delegate to whatever `test` script the
        repo defined in its own package.json — no framework-specific flags."""
        assert "npm test --if-present" in cmd_mod.NODE_NPM.unit_test[0]

    def test_no_generator_hardcodes_jest_flags_in_azure_yaml(self):
        """Belt-and-braces: rendered YAML for a JS repo must never carry a
        `--ci` flag. If any generator injects one, the run breaks on vitest."""
        yml = AzureDevOpsGenerator(**_mk_kwargs("azure_devops")).render()
        assert "--ci" not in yml, (
            f"Rendered Azure DevOps YAML still contains `--ci`: "
            f"{[l for l in yml.splitlines() if '--ci' in l]}"
        )


# ---------------------------------------------------------------------------
# 2. agent_pool applies to GitHub Actions
# ---------------------------------------------------------------------------
class TestAgentPoolAppliesToGitHubActions:
    def test_no_pool_defaults_to_github_hosted_ubuntu(self):
        yml = GitHubActionsGenerator(**_mk_kwargs("github_actions")).render()
        doc = _yaml.safe_load(yml)
        for job_id, job in doc["jobs"].items():
            assert job["runs-on"] == "ubuntu-22.04", (
                f"job {job_id} should default to GitHub-hosted ubuntu, "
                f"got {job['runs-on']!r}"
            )

    def test_pool_sets_self_hosted_label_on_every_job(self):
        yml = GitHubActionsGenerator(
            **_mk_kwargs("github_actions", pool="AIPP-Agents")
        ).render()
        doc = _yaml.safe_load(yml)
        assert doc["jobs"], "expected at least one job"
        for job_id, job in doc["jobs"].items():
            assert job["runs-on"] == ["self-hosted", "AIPP-Agents"], (
                f"job {job_id} did not honour agent_pool: {job['runs-on']}"
            )

    def test_empty_pool_string_falls_back_to_github_hosted(self):
        yml = GitHubActionsGenerator(
            **_mk_kwargs("github_actions", pool="  ")
        ).render()
        doc = _yaml.safe_load(yml)
        for job in doc["jobs"].values():
            assert job["runs-on"] == "ubuntu-22.04"


# ---------------------------------------------------------------------------
# 3. agent_pool applies to GitLab CI (per-job `tags:`)
# ---------------------------------------------------------------------------
class TestAgentPoolAppliesToGitLabCI:
    def test_no_pool_means_no_tags_on_jobs(self):
        yml = GitLabCIGenerator(**_mk_kwargs("gitlab_ci")).render()
        doc = _yaml.safe_load(yml)
        for key, job in doc.items():
            if not isinstance(job, dict) or "script" not in job:
                continue
            assert "tags" not in job, (
                f"job {key} should have no `tags:` when pool is unset; got {job.get('tags')}"
            )

    def test_pool_sets_tags_on_every_job(self):
        yml = GitLabCIGenerator(
            **_mk_kwargs("gitlab_ci", pool="AIPP-Runners")
        ).render()
        doc = _yaml.safe_load(yml)
        job_count = 0
        for key, job in doc.items():
            if not isinstance(job, dict) or "script" not in job:
                continue
            job_count += 1
            assert job.get("tags") == ["AIPP-Runners"], (
                f"job {key} did not honour agent_pool: tags={job.get('tags')}"
            )
        assert job_count > 0, "expected at least one script job"


# ---------------------------------------------------------------------------
# 4. Backwards compat — agent_pool still works for Azure DevOps
# ---------------------------------------------------------------------------
class TestAgentPoolStillWorksForAzureDevOps:
    def test_pool_becomes_ado_pool_name(self):
        yml = AzureDevOpsGenerator(
            **_mk_kwargs("azure_devops", pool="default")
        ).render()
        doc = _yaml.safe_load(yml)
        assert doc["pool"] == {"name": "default"}


# ---------------------------------------------------------------------------
# 5. UI label updated to reflect multi-platform support
# ---------------------------------------------------------------------------
class TestUILabelIsPlatformAgnostic:
    def test_agent_pool_label_no_longer_says_azure_only(self):
        src = inspect.getsource(pg.build_tab)
        # The old label said "(optional, Azure DevOps only)". Any variant of
        # that phrasing implies a scope limit that no longer applies.
        for banned in ["Azure DevOps only", "ADO only",
                       "only, Azure DevOps",
                       "only Azure"]:
            assert banned not in src, (
                f"UI still limits agent_pool to Azure DevOps ({banned!r}); "
                f"agent_pool now applies to ADO + GH Actions + GitLab CI."
            )

    def test_agent_pool_label_mentions_all_supported_platforms(self):
        src = inspect.getsource(pg.build_tab)
        low = src.lower()
        # The info tooltip must call out at least the three platforms that
        # actually honour agent_pool.
        assert "azure devops" in low
        assert "github actions" in low
        assert "gitlab" in low
