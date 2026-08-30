"""Iteration-23 tests — auth service (JWT + bcrypt) + policy bundle endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.services import auth_service


class TestPasswordHashing:
    def test_hash_and_verify_round_trip(self):
        h = auth_service.hash_password("hunter2")
        assert h.startswith("$2b$") or h.startswith("$2a$")
        assert auth_service.verify_password("hunter2", h) is True
        assert auth_service.verify_password("wrong", h) is False

    def test_verify_handles_bad_hash_gracefully(self):
        assert auth_service.verify_password("x", "not-a-hash") is False


class TestJWT:
    def test_encode_decode_round_trip(self):
        tok = auth_service.create_access_token(user_id="u1", email="a@b.c")
        payload = auth_service.decode_access_token(tok)
        assert payload["sub"] == "u1"
        assert payload["email"] == "a@b.c"
        assert payload["type"] == "access"

    def test_invalid_token_raises(self):
        import jwt
        with pytest.raises(jwt.InvalidTokenError):
            auth_service.decode_access_token("not-a-jwt")


class TestAuthRouterRegistered:
    def test_login_route_exists(self):
        from backend.server import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/auth/login" in paths
        assert "/api/auth/me" in paths
        assert "/api/auth/logout" in paths
        assert "/api/auth/oidc/enable" in paths

    def test_me_without_token_returns_401(self):
        from backend.server import app
        client = TestClient(app)
        r = client.get("/api/auth/me")
        assert r.status_code == 401


class TestPolicyBundleEndpoint:
    def test_endpoint_lists_all_three_clouds(self):
        from backend.server import app
        client = TestClient(app)
        r = client.get("/api/policy/bundle")
        assert r.status_code == 200
        data = r.json()
        assert set(data["clouds"].keys()) >= {"aws", "azure", "gcp"}
        # every cloud must return >= 4 rules
        for cloud, rules in data["clouds"].items():
            assert len(rules) >= 4, f"{cloud} has too few rules"
            for r in rules:
                assert r["package"].startswith("terraform.")
