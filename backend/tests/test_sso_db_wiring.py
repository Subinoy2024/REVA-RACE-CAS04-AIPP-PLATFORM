"""Enterprise SSO wiring tests — iteration-27.

Verify that `oidc_service.resolve_provider(...)` correctly branches:
  1. `provider_id=None` → returns env-configured provider (legacy).
  2. `provider_id="env"` → same as (1).
  3. `provider_id=<disabled UUID>` → falls through to env.
  4. `provider_id=<enabled UUID>` → returns the DB row.
  5. Both sources missing → raises `OIDCNotConfigured`.

We mock the DB via monkeypatching `_db_provider` and the settings via
`get_settings()` to avoid the sandbox's Postgres dependency.
"""

from __future__ import annotations

import uuid

import pytest

from backend.services import oidc_service as svc


class _FakeSettings:
    """Minimal shim standing in for `get_settings()` — only the OIDC
    fields the service reads."""
    oidc_provider = "off"
    oidc_client_id = ""
    oidc_client_secret = ""
    oidc_discovery_url = ""
    oidc_tenant_id = "common"
    aipp_backend_public_url = "http://localhost:8001"


def _fake_env_provider_google() -> svc.ProviderConfig:
    """Simulate an .env with a Google Workspace provider."""
    return svc.ProviderConfig(
        provider_id="env", kind="google",
        client_id="env-google-client", client_secret="env-secret",
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
        display_name="Google",
    )


@pytest.mark.asyncio
async def test_resolve_returns_env_when_no_provider_id(monkeypatch):
    monkeypatch.setattr(svc, "_env_provider", _fake_env_provider_google)
    monkeypatch.setattr(svc, "_db_provider", _async_none)
    cfg = await svc.resolve_provider(None)
    assert cfg.kind == "google"
    assert cfg.provider_id == "env"


@pytest.mark.asyncio
async def test_resolve_returns_env_when_provider_id_is_literal_env(monkeypatch):
    monkeypatch.setattr(svc, "_env_provider", _fake_env_provider_google)
    monkeypatch.setattr(svc, "_db_provider", _async_none)
    cfg = await svc.resolve_provider("env")
    assert cfg.provider_id == "env"


@pytest.mark.asyncio
async def test_resolve_uses_db_when_uuid_matches(monkeypatch):
    """If the DB has a matching provider, prefer it over env."""
    db_uuid = str(uuid.uuid4())

    async def fake_db(pid: str):
        if pid == db_uuid:
            return svc.ProviderConfig(
                provider_id=db_uuid, kind="entra",
                client_id="db-client", client_secret="db-secret",
                discovery_url="https://login.microsoftonline.com/xx/v2.0/.well-known/openid-configuration",
                tenant_id="xx", display_name="Acme Corp (Entra)",
            )
        return None

    monkeypatch.setattr(svc, "_env_provider", _fake_env_provider_google)
    monkeypatch.setattr(svc, "_db_provider", fake_db)

    cfg = await svc.resolve_provider(db_uuid)
    assert cfg.kind == "entra"
    assert cfg.provider_id == db_uuid
    assert cfg.display_name == "Acme Corp (Entra)"


@pytest.mark.asyncio
async def test_resolve_falls_back_to_env_when_db_row_missing(monkeypatch):
    monkeypatch.setattr(svc, "_env_provider", _fake_env_provider_google)
    monkeypatch.setattr(svc, "_db_provider", _async_none)
    cfg = await svc.resolve_provider(str(uuid.uuid4()))
    assert cfg.provider_id == "env"


@pytest.mark.asyncio
async def test_resolve_raises_when_no_provider_configured(monkeypatch):
    monkeypatch.setattr(svc, "_env_provider", lambda: None)
    monkeypatch.setattr(svc, "_db_provider", _async_none)
    with pytest.raises(svc.OIDCNotConfigured):
        await svc.resolve_provider(None)
    with pytest.raises(svc.OIDCNotConfigured):
        await svc.resolve_provider("env")
    with pytest.raises(svc.OIDCNotConfigured):
        await svc.resolve_provider(str(uuid.uuid4()))


def test_state_store_binds_provider_id():
    """Minting a state remembers which provider issued it, and
    consuming returns the same id exactly once."""
    st = svc._mint_state("some-provider-id")
    assert svc._consume_state(st) == "some-provider-id"
    # Second consumption must fail (single-use).
    assert svc._consume_state(st) is None


def test_state_store_expired_state_is_rejected(monkeypatch):
    """Expired states return None even before expiry-GC fires."""
    import time
    st = svc._mint_state("p1")
    # Force expiry by rewinding the recorded epoch.
    svc._STATE_STORE[st] = ("p1", time.time() - 1)
    assert svc._consume_state(st) is None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
async def _async_none(*_args, **_kw):
    return None
