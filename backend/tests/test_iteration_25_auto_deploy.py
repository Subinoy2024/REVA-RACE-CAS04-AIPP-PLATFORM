"""Iteration-25 tests — Auto-Deploy: encrypted secret storage, ADO URL
parsing, Integrations API contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.exceptions import RepositoryAccessError


class TestCryptoService:
    def test_fernet_round_trip(self):
        from backend.services.crypto_service import encrypt, decrypt
        secret = "ghp_abcdef1234567890"
        token = encrypt(secret)
        assert token != secret          # not stored in cleartext
        assert isinstance(token, str)
        assert decrypt(token) == secret

    def test_two_encryptions_produce_different_ciphertext(self):
        """Fernet includes an IV, so same plaintext → different tokens."""
        from backend.services.crypto_service import encrypt
        a = encrypt("hunter2")
        b = encrypt("hunter2")
        assert a != b

    def test_tampered_token_raises(self):
        from backend.services.crypto_service import encrypt, decrypt
        token = encrypt("original")
        tampered = token[:-2] + "AA"
        with pytest.raises(RuntimeError):
            decrypt(tampered)


class TestAzDoURLParser:
    def test_dev_azure_com(self):
        from backend.services.azdo_writer import parse_azdo_url
        r = parse_azdo_url("https://dev.azure.com/myorg/MyProject/_git/MyRepo")
        assert r.org_url == "https://dev.azure.com/myorg"
        assert r.project == "MyProject"
        assert r.repo == "MyRepo"

    def test_visualstudio_legacy_url(self):
        from backend.services.azdo_writer import parse_azdo_url
        r = parse_azdo_url("https://myorg.visualstudio.com/Proj/_git/Repo")
        assert r.org_url == "https://dev.azure.com/myorg"
        assert r.project == "Proj"
        assert r.repo == "Repo"

    def test_invalid_url_raises(self):
        from backend.services.azdo_writer import parse_azdo_url
        with pytest.raises(RepositoryAccessError):
            parse_azdo_url("https://github.com/foo/bar")


class TestIntegrationsAPIContract:
    """Contract-level checks that don't require a live DB.

    We stub-out the service layer and assert the FastAPI wiring passes
    the right inputs through.
    """

    @pytest.fixture
    def app_client(self, monkeypatch):
        # Stub `get_current_user` so we don't need a real login.
        from backend.api import integrations as api
        from backend.services import deployment_targets as svc

        async def _fake_user():
            return {"id": "u1", "email": "test@aipp.local", "role": "admin"}

        # We bypass Depends() via FastAPI's dependency_overrides
        from backend.server import app
        from backend.services.auth_service import get_current_user
        app.dependency_overrides[get_current_user] = _fake_user

        async def _fake_list(owner_email):
            return [{
                "id": "00000000-0000-0000-0000-000000000001",
                "name": "prod-repo", "platform": "github_actions",
                "repo_url": "https://github.com/x/y",
                "default_branch": "main", "extra": {},
                "is_active": True, "created_at": None,
            }]

        async def _fake_create(**kw):
            assert kw["owner_email"] == "test@aipp.local"
            assert kw["token_plain"] == "ghp_verysecrettoken"
            return {"id": "abc", "name": kw["name"], "platform": kw["platform"]}

        monkeypatch.setattr(svc, "list_targets", _fake_list)
        monkeypatch.setattr(svc, "create_target", _fake_create)

        yield TestClient(app)
        app.dependency_overrides.pop(get_current_user, None)

    def test_list_targets(self, app_client):
        r = app_client.get("/api/integrations/targets")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        assert body["targets"][0]["platform"] == "github_actions"

    def test_create_target_happy_path(self, app_client):
        r = app_client.post("/api/integrations/targets", json={
            "name": "prod-repo",
            "platform": "github_actions",
            "repo_url": "https://github.com/x/y",
            "default_branch": "main",
            "token": "ghp_verysecrettoken",
        })
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "prod-repo"

    def test_create_target_missing_token_rejected(self, app_client):
        r = app_client.post("/api/integrations/targets", json={
            "name": "prod-repo",
            "platform": "github_actions",
            "repo_url": "https://github.com/x/y",
            "default_branch": "main",
            "token": "xy",     # too short → pydantic 422
        })
        assert r.status_code == 422

    def test_deploy_rejects_bad_target_id(self, app_client):
        r = app_client.post("/api/integrations/deploy", json={
            "target_id": "not-a-uuid",
            "ci_platform": "github_actions",
            "yaml_content": "name: aipp\non: push\njobs: {}\nname2: keep-above-min-length\n",
            "mode": "pr",
        })
        assert r.status_code == 400
        assert "invalid target id" in r.text.lower()


class TestDeploymentTargetsCIPath:
    def test_ci_path_map_covers_v1_platforms(self):
        from backend.services.deployment_targets import CI_PATH
        assert CI_PATH["github_actions"].startswith(".github/workflows/")
        assert CI_PATH["azure_devops"] == "azure-pipelines.yml"


class TestPipelineGeneratorAutoDeployHooks:
    """Iteration-25 pipeline_generator wiring — the frontend module
    must expose the new helpers used by the auto-deploy panel."""

    def test_helpers_exist(self):
        import gradio as gr
        gr.Blocks.get_api_info = lambda self, *a, **k: {  # type: ignore[assignment]
            "named_endpoints": {}, "unnamed_endpoints": {},
        }
        from frontend.tabs import pipeline_generator as pg
        assert callable(pg._auto_deploy)
        assert callable(pg._list_deploy_targets)
