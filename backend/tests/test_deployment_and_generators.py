"""Regression tests for the new AIPP Commit & Deploy feature drop.

Covers:
  1. /api/deployment/branches endpoint exists, validates params.
  2. /api/deployment/commit  branch-safety guarantees:
     - Pydantic rejects empty target_branch (422)
     - github.py commit_file rejects whitespace / '*' branch (RepositoryAccessError)
     - github.py commit_file requires branch to actually exist (no fallback)
     - Unknown ci_platform is rejected (400)
  3. /api/deployment/trigger  behaviour per ci_platform:
     - github_actions accepts optional workflow_file
     - azure_devops returns 200 note (no error)
     - gitlab_ci / unsupported returns 400
  4. Deploy target selection (deploy_targets.pick_deploy_target) for all
     6 (cloud, arch) combos.
  5. commands.py has real (non-echo) commands for the main language tables.
  6. AzureDevOpsGenerator + GitHubActionsGenerator emit real production
     commands (docker buildx, npm ci, az acr login, aquasecurity/trivy-action).
"""

from __future__ import annotations

import asyncio
import os
import re

import httpx
import pytest

from backend.core.exceptions import RepositoryAccessError

BASE = os.environ.get("AIPP_INTEGRATION_URL", "http://127.0.0.1:8001").rstrip("/")


# ------------------------------------------------------------------ #
# HTTP fixture
# ------------------------------------------------------------------ #
@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=60) as c:
        yield c


# ================================================================== #
#  1. Deployment API endpoints
# ================================================================== #
class TestDeploymentBranchesEndpoint:
    """GET /api/deployment/branches"""

    def test_endpoint_exists_not_404(self, client):
        # missing params -> 422 (FastAPI validation), NOT 404
        r = client.get("/api/deployment/branches")
        assert r.status_code == 422, r.text

    def test_bogus_pat_returns_4xx_or_5xx_not_traceback(self, client):
        # Endpoint reaches the real GitHub API and gets 401. It should NOT
        # leak a Python traceback and should NOT be 404.
        r = client.get(
            "/api/deployment/branches",
            params={"repo_url": "https://github.com/pallets/flask",
                    "github_pat": "ghp_bogusbogusbogusbogus"},
        )
        assert r.status_code != 404
        body = r.json()
        assert "Traceback" not in str(body)


class TestDeploymentCommitEndpoint:
    """POST /api/deployment/commit - branch-safety contract."""

    _base_body = {
        "repo_url": "https://github.com/pallets/flask",
        "github_pat": "ghp_bogusbogusbogusbogus",
        "target_branch": "main",
        "ci_platform": "github_actions",
        "yaml_content": "name: aipp\non: push\njobs: {}\n",
        "commit_message": "chore: aipp test",
    }

    def test_empty_target_branch_rejected_with_422(self, client):
        body = dict(self._base_body, target_branch="")
        r = client.post("/api/deployment/commit", json=body)
        assert r.status_code == 422, r.text
        # Pydantic should reference target_branch
        assert "target_branch" in r.text

    def test_missing_target_branch_rejected_with_422(self, client):
        body = {k: v for k, v in self._base_body.items() if k != "target_branch"}
        r = client.post("/api/deployment/commit", json=body)
        assert r.status_code == 422

    def test_unknown_ci_platform_rejected_with_400(self, client):
        body = dict(self._base_body, ci_platform="bogus")
        r = client.post("/api/deployment/commit", json=body)
        assert r.status_code == 400, r.text
        assert "Unknown ci_platform" in r.json().get("detail", "")

    def test_known_ci_platforms_pass_validation_reach_adapter(self, client):
        """Known ci_platform passes the CI_PATH check and reaches GitHub with
        bogus PAT -> returns 400 (RepositoryAccessError) or 500, never 422."""
        for platform in ("github_actions", "azure_devops", "gitlab_ci",
                         "harness", "tekton"):
            body = dict(self._base_body, ci_platform=platform)
            r = client.post("/api/deployment/commit", json=body)
            assert r.status_code in (400, 500), (
                f"{platform}: unexpected {r.status_code}: {r.text}"
            )


class TestDeploymentTriggerEndpoint:
    """POST /api/deployment/trigger"""

    _base_body = {
        "repo_url": "https://github.com/pallets/flask",
        "github_pat": "ghp_bogusbogusbogusbogus",
        "target_branch": "main",
        "ci_platform": "github_actions",
    }

    def test_azure_devops_returns_200_note_no_error(self, client):
        body = dict(self._base_body, ci_platform="azure_devops")
        r = client.post("/api/deployment/trigger", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "azure devops" in data.get("note", "").lower() or "ado" in data.get("note", "").lower()
        assert data.get("branch") == "main"

    def test_gitlab_ci_returns_400(self, client):
        body = dict(self._base_body, ci_platform="gitlab_ci")
        r = client.post("/api/deployment/trigger", json=body)
        assert r.status_code == 400, r.text
        assert "not yet supported" in r.json()["detail"].lower()

    def test_harness_returns_400(self, client):
        body = dict(self._base_body, ci_platform="harness")
        r = client.post("/api/deployment/trigger", json=body)
        assert r.status_code == 400
        assert "not yet supported" in r.json()["detail"].lower()

    def test_github_actions_accepts_optional_workflow_file(self, client):
        """workflow_file is optional; both variants must pass Pydantic."""
        # without workflow_file
        r1 = client.post("/api/deployment/trigger", json=self._base_body)
        # with workflow_file
        r2 = client.post(
            "/api/deployment/trigger",
            json=dict(self._base_body, workflow_file="custom.yml"),
        )
        for r in (r1, r2):
            # bogus PAT means GitHub call fails; the point is that it is NOT
            # a Pydantic-422 error (i.e. schema accepts the payload).
            assert r.status_code != 422, r.text
            assert r.status_code in (200, 400, 500)


# ================================================================== #
#  2. Branch safety: unit tests against GitHubAdapter._commit_file
# ================================================================== #
class TestCommitFileBranchSafety:
    """Direct unit tests of GitHubAdapter._commit_file guard clauses."""

    @pytest.mark.asyncio
    async def test_empty_branch_raises(self):
        from backend.mcp.adapters.github import GitHubAdapter
        adapter = GitHubAdapter()
        with pytest.raises(RepositoryAccessError, match="explicit target branch"):
            await adapter._commit_file(
                url="https://github.com/pallets/flask",
                pat="ghp_x", branch="", path=".ci.yml",
                content="hi", message="test",
            )

    @pytest.mark.asyncio
    async def test_whitespace_branch_raises(self):
        from backend.mcp.adapters.github import GitHubAdapter
        adapter = GitHubAdapter()
        with pytest.raises(RepositoryAccessError, match="explicit target branch"):
            await adapter._commit_file(
                url="https://github.com/pallets/flask",
                pat="ghp_x", branch="   ", path=".ci.yml",
                content="hi", message="test",
            )

    @pytest.mark.asyncio
    async def test_asterisk_branch_raises(self):
        from backend.mcp.adapters.github import GitHubAdapter
        adapter = GitHubAdapter()
        with pytest.raises(RepositoryAccessError, match="explicit target branch"):
            await adapter._commit_file(
                url="https://github.com/pallets/flask",
                pat="ghp_x", branch="*", path=".ci.yml",
                content="hi", message="test",
            )

    def test_source_calls_get_branch_before_write(self):
        """Static assertion that _commit_file calls repo.get_branch(branch) and
        raises if it does not exist (no fallback to default_branch)."""
        import inspect
        from backend.mcp.adapters import github as gh
        src = inspect.getsource(gh.GitHubAdapter._commit_file)
        # branch existence must be verified explicitly
        assert "get_branch(branch)" in src, "must call repo.get_branch(branch)"
        # must NEVER fall back to default_branch in commit_file
        assert "default_branch" not in src, (
            "commit_file must not reference default_branch (safety violation)"
        )
        # explicit refusal message
        assert "Refusing to create it" in src


# ================================================================== #
#  3. Deploy target selection
# ================================================================== #
class TestPickDeployTarget:
    """Verify pick_deploy_target for all 6 (cloud, arch) combos."""

    @staticmethod
    def _tech(k8s: bool = False):
        from backend.models.pipeline import TechnologyProfile
        return TechnologyProfile(language="python", kubernetes_ready=k8s,
                                 helm_ready=k8s)

    @staticmethod
    def _arch(style: str = "monolith"):
        from backend.models.pipeline import ArchitectureProfile
        return ArchitectureProfile(style=style, service_count_estimate=1)

    def test_azure_monolith_picks_app_service(self):
        from backend.generators.deploy_targets import (
            AZURE_APP_SERVICE, pick_deploy_target,
        )
        from backend.models.pipeline import CloudPlatform
        t = pick_deploy_target(CloudPlatform.azure, self._arch("monolith"),
                               self._tech(k8s=False))
        assert t is AZURE_APP_SERVICE

    def test_azure_k8s_picks_aks(self):
        from backend.generators.deploy_targets import AZURE_AKS, pick_deploy_target
        from backend.models.pipeline import CloudPlatform
        t = pick_deploy_target(CloudPlatform.azure, self._arch("monolith"),
                               self._tech(k8s=True))
        assert t is AZURE_AKS

    def test_aws_monolith_picks_ecs_fargate(self):
        from backend.generators.deploy_targets import (
            AWS_ECS_FARGATE, pick_deploy_target,
        )
        from backend.models.pipeline import CloudPlatform
        t = pick_deploy_target(CloudPlatform.aws, self._arch("monolith"),
                               self._tech(k8s=False))
        assert t is AWS_ECS_FARGATE

    def test_aws_k8s_picks_eks(self):
        from backend.generators.deploy_targets import AWS_EKS, pick_deploy_target
        from backend.models.pipeline import CloudPlatform
        t = pick_deploy_target(CloudPlatform.aws, self._arch("monolith"),
                               self._tech(k8s=True))
        assert t is AWS_EKS

    def test_gcp_monolith_picks_cloud_run(self):
        from backend.generators.deploy_targets import (
            GCP_CLOUD_RUN, pick_deploy_target,
        )
        from backend.models.pipeline import CloudPlatform
        t = pick_deploy_target(CloudPlatform.gcp, self._arch("monolith"),
                               self._tech(k8s=False))
        assert t is GCP_CLOUD_RUN

    def test_gcp_k8s_picks_gke(self):
        from backend.generators.deploy_targets import GCP_GKE, pick_deploy_target
        from backend.models.pipeline import CloudPlatform
        t = pick_deploy_target(CloudPlatform.gcp, self._arch("monolith"),
                               self._tech(k8s=True))
        assert t is GCP_GKE


# ================================================================== #
#  4. commands.py has REAL commands, no echo stubs
# ================================================================== #
class TestRealCommands:
    """Verify commands.py stopped emitting echo placeholders."""

    def test_all_expected_tables_exist(self):
        from backend.generators import commands as c
        for name in ("NODE_NPM", "NODE_YARN", "PYTHON_PIP", "PYTHON_POETRY",
                     "JAVA_MAVEN", "JAVA_GRADLE", "GO_MOD", "RUST_CARGO",
                     "DOTNET"):
            assert hasattr(c, name), f"missing command table: {name}"

    def test_node_npm_has_real_build(self):
        from backend.generators.commands import NODE_NPM
        assert any("npm run build" in cmd for cmd in NODE_NPM.build), NODE_NPM.build
        assert any("npm ci" in cmd for cmd in NODE_NPM.install)

    def test_python_pip_has_real_test(self):
        from backend.generators.commands import PYTHON_PIP
        assert any("pytest" in cmd for cmd in PYTHON_PIP.unit_test)
        assert any("pip install" in cmd for cmd in PYTHON_PIP.install)

    def test_java_maven_has_real_build_and_test(self):
        from backend.generators.commands import JAVA_MAVEN
        assert any("mvn" in cmd and "package" in cmd for cmd in JAVA_MAVEN.build)
        assert any("mvn" in cmd and "test" in cmd for cmd in JAVA_MAVEN.unit_test)

    def test_go_mod_has_real_build_and_test(self):
        from backend.generators.commands import GO_MOD
        assert any(cmd.startswith("go build") for cmd in GO_MOD.build)
        assert any(cmd.startswith("go test") for cmd in GO_MOD.unit_test)

    def test_no_echo_placeholders_in_main_language_tables(self):
        """The four canonical tables from the review-request must have zero
        `echo` placeholders in their build / unit_test fields."""
        from backend.generators.commands import (
            GO_MOD, JAVA_MAVEN, NODE_NPM, PYTHON_PIP,
        )
        for tbl_name, tbl in [("NODE_NPM", NODE_NPM),
                              ("PYTHON_PIP", PYTHON_PIP),
                              ("JAVA_MAVEN", JAVA_MAVEN),
                              ("GO_MOD", GO_MOD)]:
            for stage in ("build", "unit_test"):
                for cmd in getattr(tbl, stage):
                    assert "echo" not in cmd.lower(), (
                        f"{tbl_name}.{stage} still contains echo: {cmd!r}"
                    )


# ================================================================== #
#  5. Generators emit real production YAML
# ================================================================== #
def _sample_fixture():
    """Small python-poetry azure fixture with the 6-gate default."""
    from backend.models.environment import (
        DeploymentStrategy, EnvironmentName, EnvironmentPlan, EnvironmentRule,
    )
    from backend.models.pipeline import (
        CIPlatform, CloudPlatform, PipelinePlan, PipelineStage,
        TechnologyProfile,
    )
    plan = PipelinePlan(
        ci_platform=CIPlatform.github_actions,
        cloud_platform=CloudPlatform.azure,
        stages=[PipelineStage(name="build", purpose="p"),
                PipelineStage(name="unit_test", purpose="p")],
    )
    env = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch",
                        deployment_strategy=DeploymentStrategy.rolling),
        EnvironmentRule(name=EnvironmentName.production, trigger="version_tag",
                        deployment_strategy=DeploymentStrategy.blue_green,
                        requires_approval=True),
    ])
    tech = TechnologyProfile(language="javascript", package_manager="npm",
                             container_ready=True)
    return plan, env, tech


class TestAzureDevOpsGeneratorEmitsRealCommands:

    def _render(self):
        from backend.generators.azure_devops import AzureDevOpsGenerator
        from backend.models.pipeline import CIPlatform
        plan, env, tech = _sample_fixture()
        plan.ci_platform = CIPlatform.azure_devops
        return AzureDevOpsGenerator(plan=plan, env_plan=env, tech=tech,
                                    repo_name="demo").render()

    def test_contains_real_commands(self):
        yml = self._render()
        assert "npm ci" in yml, "npm ci missing"
        assert "docker buildx build" in yml, "docker buildx missing"
        assert "az acr login" in yml, "az acr login missing"

    def test_no_echo_in_build_test_security_package_stages(self):
        """The generator MUST NOT emit `echo` stubs in the core stages.
        Deploy ladder may still contain 'echo run smoke tests here' which is
        acceptable placeholder text (excluded from this rule)."""
        yml = self._render()
        import yaml as _yaml
        doc = _yaml.safe_load(yml)
        core_stage_ids = {"build", "security", "package"}
        offenders = []
        for stage in doc.get("stages", []):
            if stage.get("stage") not in core_stage_ids:
                continue
            for job in stage.get("jobs", []):
                for step in job.get("steps", []):
                    script = step.get("script", "") or step.get("inlineScript", "")
                    if re.search(r"\becho\b", script):
                        offenders.append((stage["stage"], script))
        assert not offenders, f"echo found in core stages: {offenders}"


class TestGitHubActionsGeneratorEmitsRealCommands:

    def _render(self):
        from backend.generators.github_actions import GitHubActionsGenerator
        plan, env, tech = _sample_fixture()
        return GitHubActionsGenerator(plan=plan, env_plan=env, tech=tech,
                                      repo_name="demo").render()

    def test_contains_real_actions_and_commands(self):
        yml = self._render()
        assert "aquasecurity/trivy-action" in yml
        assert "docker buildx build" in yml
        assert "actions/setup-node@v4" in yml

    def test_no_echo_in_build_security_package_jobs(self):
        import yaml as _yaml
        yml = self._render()
        wf = _yaml.safe_load(yml)
        core_jobs = {"build", "security", "package"}
        offenders = []
        for job_id, job in (wf.get("jobs") or {}).items():
            if job_id not in core_jobs:
                continue
            for step in job.get("steps", []):
                run = step.get("run", "")
                if re.search(r"\becho\b", run):
                    offenders.append((job_id, run))
        assert not offenders, f"echo found in core jobs: {offenders}"


# ================================================================== #
#  6. Production wrapping of deploy commands (AzureCLI@2 / AWSShell / gcloud)
# ================================================================== #
def _render_ado(cloud_str: str, k8s: bool = False):
    """Render Azure DevOps YAML for the given cloud (and optional k8s signal)."""
    from backend.generators.azure_devops import AzureDevOpsGenerator
    from backend.models.environment import (
        DeploymentStrategy, EnvironmentName, EnvironmentPlan, EnvironmentRule,
    )
    from backend.models.pipeline import (
        CIPlatform, CloudPlatform, PipelinePlan, PipelineStage,
        TechnologyProfile,
    )
    plan = PipelinePlan(
        ci_platform=CIPlatform.azure_devops,
        cloud_platform=CloudPlatform(cloud_str),
        stages=[PipelineStage(name="build", purpose="p")],
    )
    env = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch",
                        deployment_strategy=DeploymentStrategy.rolling),
        EnvironmentRule(name=EnvironmentName.production, trigger="version_tag",
                        deployment_strategy=DeploymentStrategy.blue_green,
                        requires_approval=True),
    ])
    tech = TechnologyProfile(language="javascript", package_manager="npm",
                             container_ready=True,
                             kubernetes_ready=k8s, helm_ready=k8s)
    return AzureDevOpsGenerator(plan=plan, env_plan=env, tech=tech,
                                repo_name="demo").render()


class TestAzureDevOpsDeployWrapping:
    """Every cloud deploy call must be wrapped inside a proper auth task."""

    @staticmethod
    def _deploy_stages(yml: str):
        import yaml as _yaml
        doc = _yaml.safe_load(yml)
        return [s for s in doc.get("stages", [])
                if str(s.get("stage", "")).startswith("deploy_")]

    @staticmethod
    def _deploy_steps(stage) -> list:
        # deployment jobs -> strategy.runOnce.deploy.steps
        steps = []
        for job in stage.get("jobs", []):
            strat = job.get("strategy", {}) or {}
            runonce = strat.get("runOnce", {}) or {}
            deploy = runonce.get("deploy", {}) or {}
            steps.extend(deploy.get("steps", []))
        return steps

    def test_azure_deploy_uses_azurecli_task(self):
        yml = _render_ado("azure")
        stages = self._deploy_stages(yml)
        assert stages, "no deploy_* stages emitted"
        for st in stages:
            steps = self._deploy_steps(st)
            # first step must be AzureCLI@2 with the deploy commands as inlineScript
            first = steps[0]
            assert first.get("task") == "AzureCLI@2", (
                f"Azure deploy step must use AzureCLI@2, got {first}"
            )
            inputs = first.get("inputs", {})
            assert inputs.get("azureSubscription") == "${{ parameters.azureServiceConnection }}", (
                f"Deploy azureSubscription must be a compile-time parameter reference, "
                f"got {inputs.get('azureSubscription')!r}. Runtime $(VAR) syntax makes ADO "
                f"reject the pipeline in <1s with 'service connection could not be found'."
            )
            assert "az webapp" in inputs.get("inlineScript", "") \
                   or "az aks" in inputs.get("inlineScript", ""), (
                       f"AzureCLI@2 inlineScript must contain real az CLI, got {inputs.get('inlineScript')!r}"
                   )

    def test_aws_deploy_uses_aws_shell_task(self):
        yml = _render_ado("aws")
        stages = self._deploy_stages(yml)
        assert stages
        for st in stages:
            steps = self._deploy_steps(st)
            first = steps[0]
            assert first.get("task") == "AWSShellScript@1", (
                f"AWS deploy must use AWSShellScript@1, got {first}"
            )
            inputs = first.get("inputs", {})
            assert inputs.get("awsCredentials") == "${{ parameters.awsServiceConnection }}"
            assert inputs.get("regionName") == "$(AWS_REGION)"
            assert "aws ecs" in inputs.get("inlineScript", "") \
                   or "aws eks" in inputs.get("inlineScript", "")

    def test_gcp_deploy_uses_gcloud_task(self):
        yml = _render_ado("gcp")
        stages = self._deploy_stages(yml)
        assert stages
        for st in stages:
            steps = self._deploy_steps(st)
            first = steps[0]
            assert first.get("task") == "gcloud@0", (
                f"GCP deploy must use gcloud@0, got {first}"
            )
            inputs = first.get("inputs", {})
            assert inputs.get("connectedServiceNameARM") == "${{ parameters.gcpServiceConnection }}"
            assert "gcloud run deploy" in inputs.get("commandOptions", "") \
                   or "gcloud container" in inputs.get("commandOptions", "")

    def test_no_raw_shell_script_deploy_step_for_cloud_targets(self):
        """Deploy steps for cloud targets must NEVER be a raw `script:` task
        (must always be wrapped in AzureCLI@2 / AWSShellScript@1 / gcloud@0)."""
        for cloud in ("azure", "aws", "gcp"):
            yml = _render_ado(cloud)
            stages = self._deploy_stages(yml)
            for st in stages:
                steps = self._deploy_steps(st)
                # First step is the wrapped deploy call; it must NOT be a raw
                # `script:` step whose content is the deploy CLI.
                first = steps[0]
                assert "task" in first, (
                    f"{cloud}: first deploy step must be a task, got raw script: {first}"
                )
                # None of the deploy steps should contain 'az login', 'aws ecs'
                # or 'gcloud auth' as a raw `script:` string (must be inlineScript).
                for step in steps:
                    raw = step.get("script", "")
                    assert "az login" not in raw
                    assert "aws ecs" not in raw
                    assert "gcloud auth" not in raw

    def test_smoke_test_is_real_curl_not_echo(self):
        """Smoke test must be a real curl to $APP_HEALTH_URL/health, not echo."""
        for cloud in ("azure", "aws", "gcp"):
            yml = _render_ado(cloud)
            assert "curl -fsS $APP_HEALTH_URL/health" in yml, (
                f"[{cloud}] smoke test curl not found in YAML"
            )
            assert "run smoke tests here" not in yml, (
                f"[{cloud}] echo placeholder for smoke test still present"
            )
            assert "smoke test failed" in yml

    def test_pipeline_has_four_top_level_stages(self):
        """build, security, package + one deploy_* stage per env rule."""
        import yaml as _yaml
        yml = _render_ado("azure")
        doc = _yaml.safe_load(yml)
        stage_ids = [s.get("stage") for s in doc.get("stages", [])]
        assert "build" in stage_ids
        assert "security" in stage_ids
        assert "package" in stage_ids
        deploys = [s for s in stage_ids if s.startswith("deploy_")]
        # fixture has 2 env rules: development + production
        assert len(deploys) == 2, f"expected 2 deploy_ stages, got {deploys}"

    def test_deploy_jobs_use_deployment_and_runonce(self):
        """Each deploy stage must be a `deployment:` job (not `job:`) with
        `environment:` set and `strategy: runOnce`."""
        import yaml as _yaml
        yml = _render_ado("azure")
        doc = _yaml.safe_load(yml)
        deploys = [s for s in doc.get("stages", [])
                   if str(s.get("stage", "")).startswith("deploy_")]
        assert deploys
        for stage in deploys:
            for job in stage.get("jobs", []):
                assert "deployment" in job, f"job must have 'deployment' key: {job}"
                assert "job" not in job, f"deploy job must NOT use raw 'job:' key: {job}"
                assert job.get("environment"), f"missing environment: {job}"
                assert "runOnce" in (job.get("strategy") or {}), (
                    f"deploy job must use strategy.runOnce: {job}"
                )

    def test_azure_acr_login_uses_compile_time_service_connection(self):
        """The ACR login step in the `package` stage must use the compile-time
        `${{ parameters.azureServiceConnection }}` expression — runtime
        $(AZURE_SUBSCRIPTION) causes ADO to reject the pipeline in <1s with
        'service connection could not be found'."""
        yml = _render_ado("azure")
        assert "${{ parameters.azureServiceConnection }}" in yml, (
            "Package stage ACR login must reference "
            "${{ parameters.azureServiceConnection }} (compile-time)"
        )
        # Runtime SC references must NOT appear anywhere in the YAML.
        for banned in ("$(AZURE_SUBSCRIPTION)", "$(AZURE_SERVICE_CONNECTION)",
                       "$(AWS_SERVICE_CONNECTION)", "$(GCP_SERVICE_CONNECTION)"):
            assert banned not in yml, (
                f"YAML must not use runtime `{banned}` for a service-connection "
                f"reference — ADO resolves SCs at compile time only."
            )

    def test_azure_k8s_also_wrapped_in_azurecli(self):
        """When kubernetes_ready is True, deploy target is AKS which uses
        `az aks get-credentials` + helm; the whole block must still be wrapped
        in a single AzureCLI@2 task."""
        yml = _render_ado("azure", k8s=True)
        stages = self._deploy_stages(yml)
        for st in stages:
            steps = self._deploy_steps(st)
            first = steps[0]
            assert first.get("task") == "AzureCLI@2"
            inline = first.get("inputs", {}).get("inlineScript", "")
            assert "az aks get-credentials" in inline
            assert "helm upgrade" in inline


# ================================================================== #
#  7. Setup instructions markdown returned to the UI after commit
# ================================================================== #
class TestSetupInstructionsMarkdown:
    """The frontend _setup_instructions returned in the second output of
    _commit must contain the platform-specific one-time setup steps."""

    def test_azure_devops_setup_contains_required_keys(self):
        from frontend.tabs.pipeline_generator import _setup_instructions
        md = _setup_instructions("azure_devops", "release/1.0.0")
        low = md.lower()
        # SC creation instructions must still be present; we now instruct
        # users to name the connection `azure-service-connection` to match
        # the pipeline parameter default.
        assert "azure-service-connection" in md
        assert "service connection" in low
        assert "AZURE_WEBAPP_NAME" in md
        assert "approvals" in low
        assert "environments" in low
        # branch echoed
        assert "release/1.0.0" in md

    def test_github_actions_setup_returns_markdown(self):
        from frontend.tabs.pipeline_generator import _setup_instructions
        md = _setup_instructions("github_actions", "main")
        assert isinstance(md, str) and len(md) > 50
        assert "github" in md.lower() or "actions" in md.lower()

    def test_unknown_ci_platform_returns_generic_note(self):
        from frontend.tabs.pipeline_generator import _setup_instructions
        md = _setup_instructions("tekton", "feature/x")
        assert "feature/x" in md
        assert "tekton" in md.lower()



# ================================================================== #
#  8. Regression tests for the 3 newly-rewritten generators
#     (GitLab CI, Harness, Tekton) -- production readiness sweep
# ================================================================== #
def _fixture_4_envs(cloud_str: str = "azure", k8s: bool = False):
    """Fixture with all 4 environments + a Node/npm stack. Used to verify
    the newly-rewritten GitLab / Harness / Tekton generators."""
    from backend.models.environment import (
        DeploymentStrategy, EnvironmentName, EnvironmentPlan, EnvironmentRule,
    )
    from backend.models.pipeline import (
        CIPlatform, CloudPlatform, PipelinePlan, PipelineStage,
        TechnologyProfile,
    )
    plan = PipelinePlan(
        ci_platform=CIPlatform.github_actions,
        cloud_platform=CloudPlatform(cloud_str),
        stages=[PipelineStage(name="build", purpose="p")],
    )
    env = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch",
                        deployment_strategy=DeploymentStrategy.rolling),
        EnvironmentRule(name=EnvironmentName.qa, trigger="feature_branch",
                        deployment_strategy=DeploymentStrategy.rolling),
        EnvironmentRule(name=EnvironmentName.staging, trigger="release_branch",
                        deployment_strategy=DeploymentStrategy.blue_green),
        EnvironmentRule(name=EnvironmentName.production, trigger="version_tag",
                        deployment_strategy=DeploymentStrategy.blue_green,
                        requires_approval=True),
    ])
    tech = TechnologyProfile(language="javascript", package_manager="npm",
                             container_ready=True,
                             kubernetes_ready=k8s, helm_ready=k8s)
    return plan, env, tech


# Regex that matches echo-as-placeholder (`echo 'Run X'` / `echo 'run X'`)
# without matching legitimate error messages such as
# `echo 'smoke test failed' && exit 1`.
_ECHO_STUB_RE = re.compile(r"echo\s+['\"](run|Run)\s+[A-Za-z][A-Za-z0-9_ -]*['\"]")


class TestGitLabCIGeneratorProduction:
    """GitLab CI generator: production readiness after the rewrite."""

    def _render(self, cloud="azure", k8s=False):
        from backend.generators.gitlab_ci import GitLabCIGenerator
        plan, env, tech = _fixture_4_envs(cloud, k8s)
        return GitLabCIGenerator(plan=plan, env_plan=env, tech=tech,
                                 repo_name="demo").render()

    def test_has_npm_ci_and_real_container_build(self):
        yml = self._render()
        assert "npm ci" in yml
        assert "docker buildx build" in yml

    def test_has_trivy_scan(self):
        yml = self._render()
        assert "trivy image" in yml

    def test_has_curl_smoke_test(self):
        yml = self._render()
        assert "curl -fsS $APP_HEALTH_URL/health" in yml
        # each of the 4 env stages that requested a smoke test must have it
        # (all rules default smoke_test=True)
        assert yml.count("curl -fsS $APP_HEALTH_URL/health") >= 4

    def test_no_echo_stub_placeholders(self):
        yml = self._render()
        offenders = _ECHO_STUB_RE.findall(yml)
        assert not offenders, f"echo-as-placeholder detected: {offenders}"

    def test_stages_block_and_gitlab_native_constructs(self):
        import yaml as _yaml
        doc = _yaml.safe_load(self._render())
        # Top-level `stages:` list
        assert "stages" in doc and isinstance(doc["stages"], list)
        # container-build job uses services: [docker:24-dind]
        assert doc["container_build_scan_push"]["services"] == ["docker:24-dind"]
        # rules use $CI_COMMIT_BRANCH / $CI_COMMIT_TAG expressions
        dev = doc["deploy_development"]
        assert dev["rules"][0]["if"].startswith("$CI_COMMIT_BRANCH")
        # requires_approval => when: manual on production
        prod = doc["deploy_production"]
        assert prod["when"] == "manual"

    def test_supports_all_4_environments(self):
        import yaml as _yaml
        doc = _yaml.safe_load(self._render())
        deploys = [s for s in doc["stages"] if s.startswith("deploy_")]
        assert set(deploys) == {"deploy_development", "deploy_qa",
                                "deploy_staging", "deploy_production"}

    def test_azure_monolith_uses_az_webapp(self):
        yml = self._render("azure", k8s=False)
        assert "az webapp" in yml

    def test_azure_k8s_uses_helm_and_aks_get_credentials(self):
        yml = self._render("azure", k8s=True)
        assert "helm upgrade" in yml
        assert "az aks get-credentials" in yml


class TestHarnessGeneratorProduction:
    """Harness generator: production readiness after the rewrite."""

    def _render(self, cloud="azure", k8s=False):
        from backend.generators.harness import HarnessGenerator
        plan, env, tech = _fixture_4_envs(cloud, k8s)
        return HarnessGenerator(plan=plan, env_plan=env, tech=tech,
                                repo_name="demo").render()

    def test_has_npm_ci_and_container_build_step(self):
        yml = self._render()
        assert "npm ci" in yml
        # Harness native container step (not raw docker buildx)
        assert "BuildAndPushDockerRegistry" in yml

    def test_has_trivy_scan(self):
        yml = self._render()
        assert "trivy image" in yml

    def test_has_curl_smoke_test(self):
        yml = self._render()
        assert "curl -fsS $APP_HEALTH_URL/health" in yml

    def test_no_echo_stub_placeholders(self):
        yml = self._render()
        offenders = _ECHO_STUB_RE.findall(yml)
        assert not offenders, f"echo-as-placeholder detected: {offenders}"

    def test_ci_stage_type_and_cd_stage_types(self):
        import yaml as _yaml
        doc = _yaml.safe_load(self._render())
        stages = doc["pipeline"]["stages"]
        types = [s["stage"]["type"] for s in stages]
        assert types[0] == "CI"
        # every subsequent stage must be a Custom (or Deployment) stage
        assert all(t in {"Custom", "Deployment"} for t in types[1:])

    def test_production_stage_has_harness_approval_step(self):
        import yaml as _yaml
        doc = _yaml.safe_load(self._render())
        prod = next(s for s in doc["pipeline"]["stages"]
                    if s["stage"]["identifier"] == "deploy_production")
        step_types = [step["step"]["type"]
                      for step in prod["stage"]["spec"]["execution"]["steps"]]
        assert step_types[0] == "HarnessApproval"

    def test_uses_trigger_branch_condition(self):
        yml = self._render()
        assert "<+trigger.branch>" in yml or "<+trigger.tag>" in yml

    def test_supports_all_4_environments(self):
        import yaml as _yaml
        doc = _yaml.safe_load(self._render())
        ids = {s["stage"]["identifier"] for s in doc["pipeline"]["stages"]}
        for env in ("deploy_development", "deploy_qa", "deploy_staging",
                    "deploy_production"):
            assert env in ids, f"missing {env}"

    def test_azure_monolith_uses_az_webapp(self):
        assert "az webapp" in self._render("azure", k8s=False)

    def test_azure_k8s_uses_helm_and_aks_get_credentials(self):
        yml = self._render("azure", k8s=True)
        assert "helm upgrade" in yml
        assert "az aks get-credentials" in yml


class TestTektonGeneratorProduction:
    """Tekton generator: production readiness after the rewrite."""

    def _render(self, cloud="azure", k8s=False):
        from backend.generators.tekton import TektonGenerator
        plan, env, tech = _fixture_4_envs(cloud, k8s)
        return TektonGenerator(plan=plan, env_plan=env, tech=tech,
                               repo_name="demo").render()

    def test_has_npm_ci_and_real_container_build(self):
        yml = self._render()
        assert "npm ci" in yml
        assert "buildah bud" in yml

    def test_has_trivy_scan(self):
        yml = self._render()
        assert "trivy image" in yml

    def test_has_curl_smoke_test(self):
        yml = self._render()
        assert "curl -fsS $APP_HEALTH_URL/health" in yml

    def test_no_echo_stub_placeholders(self):
        yml = self._render()
        offenders = _ECHO_STUB_RE.findall(yml)
        assert not offenders, f"echo-as-placeholder detected: {offenders}"

    def test_multi_document_yaml(self):
        import yaml as _yaml
        docs = list(_yaml.safe_load_all(self._render()))
        # 6 CI tasks + 4 deploy tasks + 1 pipeline = 11 documents
        assert len(docs) >= 8, f"expected multi-doc YAML, got {len(docs)}"
        kinds = {d.get("kind") for d in docs if d}
        assert "Task" in kinds and "Pipeline" in kinds

    def test_build_task_uses_language_specific_image(self):
        import yaml as _yaml
        docs = list(_yaml.safe_load_all(self._render()))
        build = next(d for d in docs
                     if d.get("kind") == "Task"
                     and d["metadata"]["name"] == "aipp-build")
        img = build["spec"]["steps"][0]["image"]
        # Node/JS stack must use node:20-bullseye, not alpine:3
        assert img == "node:20-bullseye", f"unexpected build image: {img}"

    def test_container_build_task_uses_buildah_image(self):
        import yaml as _yaml
        docs = list(_yaml.safe_load_all(self._render()))
        cb = next(d for d in docs
                  if d.get("kind") == "Task"
                  and d["metadata"]["name"] == "aipp-container-build-push")
        img = cb["spec"]["steps"][0]["image"]
        assert "buildah" in img, f"container build must use buildah image, got {img}"

    def test_pipeline_tasks_have_runafter_chain(self):
        import yaml as _yaml
        docs = list(_yaml.safe_load_all(self._render()))
        pipeline = next(d for d in docs if d.get("kind") == "Pipeline")
        tasks = pipeline["spec"]["tasks"]
        # first task has no runAfter, all subsequent must
        for t in tasks[1:]:
            assert t.get("runAfter"), f"task {t['name']} missing runAfter"

    def test_when_clauses_reference_params_branch(self):
        yml = self._render()
        assert "$(params.BRANCH)" in yml

    def test_supports_all_4_environments(self):
        import yaml as _yaml
        docs = list(_yaml.safe_load_all(self._render()))
        pipeline = next(d for d in docs if d.get("kind") == "Pipeline")
        names = {t["name"] for t in pipeline["spec"]["tasks"]}
        for env in ("deploy-development", "deploy-qa", "deploy-staging",
                    "deploy-production"):
            assert env in names, f"missing {env}"

    def test_azure_monolith_uses_az_webapp(self):
        assert "az webapp" in self._render("azure", k8s=False)

    def test_azure_k8s_uses_helm_and_aks_get_credentials(self):
        yml = self._render("azure", k8s=True)
        assert "helm upgrade" in yml
        assert "az aks get-credentials" in yml


class TestAllFiveGeneratorsProductionSweep:
    """Cross-generator sweep: every generator must satisfy the same
    production baseline for a Node/npm Azure stack."""

    @pytest.fixture(scope="class")
    def rendered(self):
        from backend.generators.azure_devops import AzureDevOpsGenerator
        from backend.generators.github_actions import GitHubActionsGenerator
        from backend.generators.gitlab_ci import GitLabCIGenerator
        from backend.generators.harness import HarnessGenerator
        from backend.generators.tekton import TektonGenerator
        plan, env, tech = _fixture_4_envs("azure", k8s=False)
        return {
            "ado":     AzureDevOpsGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render(),
            "gha":     GitHubActionsGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render(),
            "gitlab":  GitLabCIGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render(),
            "harness": HarnessGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render(),
            "tekton":  TektonGenerator(plan=plan, env_plan=env, tech=tech, repo_name="demo").render(),
        }

    def test_all_have_npm_ci(self, rendered):
        for name, yml in rendered.items():
            assert "npm ci" in yml, f"[{name}] missing npm ci"

    def test_all_have_trivy_scan(self, rendered):
        for name, yml in rendered.items():
            assert "trivy" in yml, f"[{name}] missing trivy scan"

    def test_all_have_curl_smoke_test(self, rendered):
        for name, yml in rendered.items():
            assert "curl -fsS" in yml, f"[{name}] missing curl smoke test"

    def test_all_have_real_container_build(self, rendered):
        # Each generator emits its native "real build" primitive
        assert "docker buildx build" in rendered["ado"]
        assert "docker buildx build" in rendered["gha"]
        assert "docker buildx build" in rendered["gitlab"]
        assert "BuildAndPushDockerRegistry" in rendered["harness"]
        assert "buildah bud" in rendered["tekton"]

    def test_no_echo_stub_placeholders_anywhere(self, rendered):
        for name, yml in rendered.items():
            offenders = _ECHO_STUB_RE.findall(yml)
            assert not offenders, f"[{name}] echo-as-placeholder: {offenders}"

    def test_all_reach_az_webapp_for_azure_monolith(self, rendered):
        for name, yml in rendered.items():
            assert "az webapp" in yml, f"[{name}] missing az webapp deploy"
