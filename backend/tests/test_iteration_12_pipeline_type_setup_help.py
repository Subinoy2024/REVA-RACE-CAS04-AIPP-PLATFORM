"""Iteration-12 regression tests — pipeline-type-aware setup instructions.

Bug reported by the user (screenshot):
  User selected `pipeline_type = ci` (CI only) but the post-commit
  "One-time Azure DevOps setup" panel still asked them to configure
  service connections, deploy variables (AZURE_WEBAPP_NAME, AZURE_RG…)
  and environments — all of which are CD concerns, not CI.

Fix:
  1. `_setup_instructions` now takes a `pipeline_type` argument and
     branches on `ci` / `cd` / `infra` / `all_in_one`.
  2. `_commit` accepts `pipeline_type` from a new `pipeline_type_state`
     and forwards it.
  3. `_generate` emits `pipeline_type` as the 11th output element so the
     state stays in sync with whatever the user selected.
"""

from __future__ import annotations

import inspect
import re

from frontend.tabs import pipeline_generator as pg


class TestSetupInstructionsCIOnly:
    def test_ci_azure_devops_does_not_mention_deploy_variables(self):
        md = pg._setup_instructions("azure_devops", "main", "ci")
        # CI-only pipelines still push a container image, which requires a
        # service connection for ACR login. What they don't need is the CD
        # variables (Web App, RG, environments, approvals).
        assert "AZURE_WEBAPP_NAME" not in md
        assert "AZURE_RG" not in md
        assert "Environments" not in md, (
            "CI-only pipelines don't need dev/qa/staging/prod ADO environments"
        )
        assert "Approval" not in md and "approval check" not in md

    def test_ci_azure_devops_mentions_registry_and_sc_name(self):
        md = pg._setup_instructions("azure_devops", "main", "ci")
        assert "REGISTRY_NAME" in md or "ACR" in md
        # CI still needs a Service Connection for ACR push — matches YAML
        # parameter default.
        assert "azure-service-connection" in md
        assert "**CI-only**" in md

    def test_ci_github_actions_only_asks_for_registry_creds(self):
        md = pg._setup_instructions("github_actions", "main", "ci")
        assert "REGISTRY" in md.upper()
        assert "AZURE_CREDENTIALS" not in md
        assert "AWS_ACCESS_KEY_ID" not in md
        assert "GCP_SA_KEY" not in md
        assert "**CI-only**" in md

    def test_ci_unknown_platform_still_returns_ci_only_hint(self):
        md = pg._setup_instructions("harness", "release", "ci")
        assert "CI-only" in md
        assert "container registry" in md.lower()


class TestSetupInstructionsCDOnly:
    def test_cd_azure_devops_still_asks_for_service_connection(self):
        md = pg._setup_instructions("azure_devops", "main", "cd")
        # Now the SC is expressed by exact name (matching the YAML parameter
        # default) rather than a variable reference.
        assert "azure-service-connection" in md
        assert "AZURE_WEBAPP_NAME" in md
        # CD-only must NOT ask users to also set up CI-side registry admin creds
        assert "ACR_USERNAME" not in md
        assert "**CD-only**" in md

    def test_cd_github_actions_asks_for_cloud_creds_only(self):
        md = pg._setup_instructions("github_actions", "main", "cd")
        assert ("AZURE_CREDENTIALS" in md
                or "AWS_ACCESS_KEY_ID" in md
                or "GCP_SA_KEY" in md)
        assert "**CD-only**" in md


class TestSetupInstructionsInfraOnly:
    def test_infra_mentions_terraform_backend_and_no_registry(self):
        md = pg._setup_instructions("azure_devops", "main", "infra")
        assert "Terraform" in md
        # infra needs state backend, not container registry
        assert "REGISTRY_NAME" not in md
        assert "AZURE_WEBAPP_NAME" not in md
        assert "state backend" in md.lower() or "S3" in md or "GCS" in md

    def test_infra_lists_cloud_creds_per_provider(self):
        md = pg._setup_instructions("github_actions", "main", "infra")
        # Iteration 17 moved to a production-grade multi-stage pipeline using a
        # compile-time service connection, so per-cloud shell env vars are no
        # longer the primary auth surface. The instructions must still mention
        # the three cloud service-connection names.
        assert ("azure-service-connection" in md
                or "aws-service-connection" in md
                or "gcp-service-connection" in md)


class TestSetupInstructionsAllInOne:
    def test_all_in_one_keeps_original_azure_setup_block(self):
        md = pg._setup_instructions("azure_devops", "main", "all_in_one")
        # Original CI+CD block — service connection is now expressed by
        # exact name (matches YAML parameter default) rather than a var.
        for token in [
            "azure-service-connection", "AZURE_WEBAPP_NAME", "AZURE_RG",
            "REGISTRY_NAME", "Environments", "approval check",
        ]:
            assert token in md, f"all_in_one setup missing `{token}`"

    def test_default_argument_is_all_in_one(self):
        # Back-compat safety: any old caller that doesn't pass pipeline_type
        # should get the full CI+CD block.
        md_default = pg._setup_instructions("azure_devops", "main")
        md_all = pg._setup_instructions("azure_devops", "main", "all_in_one")
        assert md_default == md_all


class TestCommitPassesPipelineType:
    def test_commit_signature_has_pipeline_type_as_last_param(self):
        params = list(inspect.signature(pg._commit).parameters)
        assert params == [
            "repo_url", "pat", "target_branch", "ci",
            "yaml_text", "message", "pipeline_type",
        ], f"unexpected _commit signature: {params}"

    def test_commit_forwards_pipeline_type_to_setup_instructions(self, monkeypatch):
        """When _commit runs, the setup_help output must reflect the
        pipeline_type it was called with (not the hardcoded all-in-one)."""
        def fake_post(path, json=None, **_kw):
            return {"ok": True, "commit_sha": "abc12345",
                    "action": "updated", "commit_url": "https://x"}

        monkeypatch.setattr(pg, "post", fake_post)
        _msg, setup_md = pg._commit(
            "https://github.com/o/n", "ghp_x", "main", "azure_devops",
            "stages: []", "chore", "ci",
        )
        assert "CI-only" in setup_md
        # CI-only setup no longer configures dev/qa/staging/prod environments
        # or Web App variables — just registry + SC for ACR login.
        assert "AZURE_WEBAPP_NAME" not in setup_md
        assert "Environments" not in setup_md


class TestGenerateEmitsPipelineTypeAsLastFrameElement:
    def test_final_frame_ends_with_pipeline_type(self, monkeypatch):
        def fake_sse(path, *, json_body, **_kw):
            yield {"kind": "result", "payload": {
                "pipeline": {"yaml_content": "stages: []", "filename": "x.yml"},
                "explanation": "e", "plan": {}, "validation": {},
                "analysis": {"owner": "o", "name": "n"},
                "generation_seconds": 1.0,
            }}
            yield {"kind": "done"}

        monkeypatch.setattr(pg, "sse_post", fake_sse)
        frames = list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "azure_devops", "azure", "unspecified", "ci", "", "terraform", "",
        ))
        # Iteration-25 added the auto-deploy panel visibility update; the
        # directive-trace iteration adds a 13th element (directive_md
        # markdown). Element 10 remains the pipeline_type state — the
        # trailing gr.update + directive_md are appended after it.
        assert len(frames[-1]) == 13
        # Element 10 (index-10 in a 13-tuple) is the pipeline_type state.
        assert frames[-1][10] == "ci"

    def test_idle_frame_has_matching_arity(self):
        # All three tuple builders must have the same length so Gradio
        # doesn't crash on a partial update.
        assert (len(pg._idle_outputs())
                == len(pg._error_outputs("boom"))
                == 13)


class TestBuildTabWiring:
    def test_pipeline_type_state_is_declared(self):
        src = inspect.getsource(pg.build_tab)
        assert "pipeline_type_state" in src

    def test_generate_click_outputs_include_pipeline_type_state(self):
        src = inspect.getsource(pg.build_tab)
        m = re.search(
            r"btn\.click\(\s*_generate\s*,\s*inputs\s*=\s*\[[^\]]*\]\s*,\s*"
            r"outputs\s*=\s*\[([^\]]*)\]",
            src, re.DOTALL,
        )
        assert m, "Could not locate btn.click(_generate, ...) wiring"
        outputs = [tok.strip() for tok in m.group(1).split(",") if tok.strip()]
        assert "pipeline_type_state" in outputs, (
            f"btn.click outputs missing pipeline_type_state. Got: {outputs}"
        )

    def test_commit_click_inputs_include_pipeline_type_state(self):
        src = inspect.getsource(pg.build_tab)
        m = re.search(
            r"commit_btn\.click\(\s*_commit\s*,\s*inputs\s*=\s*\[([^\]]*)\]",
            src, re.DOTALL,
        )
        assert m, "Could not locate commit_btn.click(_commit, ...) wiring"
        inputs = [tok.strip() for tok in m.group(1).split(",") if tok.strip()]
        assert "pipeline_type_state" in inputs, (
            f"commit_btn.click inputs missing pipeline_type_state. Got: {inputs}"
        )
