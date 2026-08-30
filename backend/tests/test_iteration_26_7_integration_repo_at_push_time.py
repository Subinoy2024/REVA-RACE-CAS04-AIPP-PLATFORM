"""Iteration-26.7 · Integrations = tool credential only.

Locks in the refactor: repo_url is picked at push time on the Pipeline
Generator, not saved on the Integration. Integration only carries the tool
credential (PAT).
"""

from __future__ import annotations

from pathlib import Path

import pytest


PG_SRC = Path("/app/frontend/tabs/pipeline_generator.py").read_text()
INT_SRC = Path("/app/frontend/tabs/integrations.py").read_text()


# ---------- Backend contract ----------

def test_target_create_repo_url_optional():
    from backend.api.integrations import TargetCreate
    # No repo_url given — must be accepted, default empty string.
    body = TargetCreate(
        name="Tool cred",
        platform="github_actions",
        token="ghp_abcdefg1234567890",
    )
    assert body.repo_url == ""
    assert body.default_branch == "main"


def test_deploy_request_accepts_repo_url_override():
    from backend.api.integrations import DeployRequest
    body = DeployRequest(
        target_id="00000000-0000-0000-0000-000000000000",
        ci_platform="github_actions",
        yaml_content="name: build\non: push\njobs:\n  b:\n    runs-on: ubuntu\n    steps: [{run: 'echo hi'}]",
        mode="pr",
        repo_url="https://github.com/my-org/deploy-repo",
        branch="main",
    )
    assert body.repo_url == "https://github.com/my-org/deploy-repo"


def test_deploy_service_signature_has_repo_url_override():
    """`deployment_targets.deploy()` must accept `repo_url_override`."""
    import inspect
    from backend.services.deployment_targets import deploy
    sig = inspect.signature(deploy)
    assert "repo_url_override" in sig.parameters


# ---------- Frontend UI wiring ----------

def test_integrations_form_no_longer_asks_for_repo_url():
    """Onboarding an integration must NOT prompt for a repo URL upfront."""
    assert "Deployment repo URL" not in INT_SRC.split("Deploy Integrations")[1] \
        if "Deploy Integrations" in INT_SRC else True
    # More robust: `repo_in = gr.Textbox` should be gone.
    assert "repo_in = gr.Textbox(label=\"Deployment repo URL\"" not in INT_SRC


def test_pipeline_generator_has_deployment_repo_url_input():
    """Push time is where the repo URL is chosen — the field is on PG."""
    assert 'elem_id="pg-ad-repo-url"' in PG_SRC
    assert '"Deployment repo URL"' in PG_SRC


def test_auto_deploy_client_sends_repo_url():
    """Client `_auto_deploy` must include repo_url in the POST body."""
    assert '"repo_url": repo_url.strip()' in PG_SRC


def test_auto_deploy_rejects_missing_repo_url():
    assert "Enter the **Deployment repo URL**" in PG_SRC
