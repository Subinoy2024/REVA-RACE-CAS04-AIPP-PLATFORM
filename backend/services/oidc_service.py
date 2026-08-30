"""OIDC (OpenID Connect) service — Google Workspace, Azure AD (Entra ID),
or any OIDC-compliant IdP.

Design:
  * Two provider sources coexist:
      (a) **Env** — legacy path driven by `OIDC_PROVIDER` in `.env`. Kept
          for backwards compatibility; `provider_id == "env"` selects it.
      (b) **DB** — Enterprise SSO tab writes `identity_providers` rows;
          the login page's "Sign in with X" button carries the DB row's
          UUID as `?provider_id=<uuid>`.
  * Standard **Authorization Code Flow with PKCE-lite** (thesis scope —
    we use `state` + short in-memory nonce store instead of full PKCE).
  * Callback ends with a redirect to `AIPP_PUBLIC_URL/?token=<jwt>` so
    Gradio can pick the JWT out of the URL query and stash it in
    `gr.State`.

Endpoints exposed by `api/auth.py`:
  GET  /api/auth/oidc/login?provider_id=<uuid|env>  → 302 → provider auth URL
  GET  /api/auth/oidc/callback                       → exchange → mint JWT → 302 → UI
  GET  /api/auth/oidc/status                         → JSON: {enabled, provider, ready}
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional

import httpx

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


_PROVIDER_DEFAULTS = {
    "google": "https://accounts.google.com/.well-known/openid-configuration",
    # Azure AD / Entra ID — tenant is templated at runtime.
    "azure":  "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
    # Iteration-27 · DB-configured providers use `kind` values:
    "entra":  "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration",
    "oidc":   "",  # DB row MUST supply discovery_url
}

# In-memory state store — value is (provider_id, expires_at_epoch).
# Thesis scope. Redis in production (see PRODUCTION_HARDENING §2.1).
_STATE_STORE: Dict[str, tuple[str, float]] = {}
_STATE_TTL_SECONDS = 5 * 60


class OIDCNotConfigured(Exception):
    pass


class OIDCError(Exception):
    pass


# ---------------------------------------------------------------------------
# ProviderConfig — the normalised shape both env and DB paths converge on
# ---------------------------------------------------------------------------
@dataclass
class ProviderConfig:
    provider_id: str            # "env" for legacy .env, or the DB row UUID
    kind: str                   # google | azure | entra | oidc
    client_id: str
    client_secret: str
    discovery_url: str
    tenant_id: Optional[str] = None
    display_name: Optional[str] = None


def _env_provider() -> Optional[ProviderConfig]:
    """Load the legacy .env-driven provider config, or None if disabled."""
    s = get_settings()
    if (
        s.oidc_provider not in _PROVIDER_DEFAULTS
        or not s.oidc_client_id
        or not s.oidc_client_secret
    ):
        return None
    disc = s.oidc_discovery_url or _PROVIDER_DEFAULTS[s.oidc_provider].format(
        tenant=s.oidc_tenant_id or "common"
    )
    return ProviderConfig(
        provider_id="env",
        kind=s.oidc_provider,
        client_id=s.oidc_client_id,
        client_secret=s.oidc_client_secret,
        discovery_url=disc,
        tenant_id=s.oidc_tenant_id,
        display_name=s.oidc_provider.title(),
    )


async def _db_provider(provider_id: str) -> Optional[ProviderConfig]:
    """Load a DB-configured provider by UUID, decrypting its secret.

    Returns None if the row doesn't exist or is disabled. Caller decides
    whether to fall through to the env path or 501.
    """
    import uuid as _uuid
    try:
        pid = _uuid.UUID(provider_id)
    except (ValueError, TypeError):
        return None
    from backend.database.connection import session_scope
    from backend.database.models import IdentityProvider
    from backend.services.crypto_service import decrypt
    from sqlalchemy import select
    async with session_scope() as sess:
        row = (await sess.execute(
            select(IdentityProvider).where(IdentityProvider.id == pid)
        )).scalar_one_or_none()
    if row is None or not row.enabled:
        return None
    disc = row.discovery_url or _PROVIDER_DEFAULTS.get(row.kind, "").format(
        tenant=row.tenant_id or "common"
    )
    if not disc:
        return None
    try:
        secret = decrypt(row.client_secret_enc)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("oidc.db: cannot decrypt provider %s: %s", provider_id, e)
        return None
    return ProviderConfig(
        provider_id=str(row.id),
        kind=row.kind,
        client_id=row.client_id,
        client_secret=secret,
        discovery_url=disc,
        tenant_id=row.tenant_id,
        display_name=row.display_name,
    )


async def resolve_provider(provider_id: Optional[str]) -> ProviderConfig:
    """Load a provider config by ID, falling back to env for `None|"env"`.

    Raises OIDCNotConfigured if no provider matches.
    """
    if provider_id and provider_id != "env":
        cfg = await _db_provider(provider_id)
        if cfg is not None:
            return cfg
    cfg = _env_provider()
    if cfg is not None:
        return cfg
    raise OIDCNotConfigured(
        "No OIDC provider is configured — either fill OIDC_* in .env or "
        "add a provider under Enterprise SSO."
    )


def is_enabled() -> bool:
    """Kept for the /oidc/status endpoint — checks legacy .env only.
    Use `resolve_provider(...)` for the DB-aware path."""
    return _env_provider() is not None


def status_dict() -> dict:
    """Legacy env-only status. Kept for backward compat with /oidc/status.
    DB providers are exposed by `/api/auth/identity-providers/public`."""
    s = get_settings()
    return {
        "enabled": is_enabled(),
        "provider": s.oidc_provider if s.oidc_provider in _PROVIDER_DEFAULTS else "off",
        "client_id_set": bool(s.oidc_client_id),
        "client_secret_set": bool(s.oidc_client_secret),
    }


def _redirect_uri() -> str:
    s = get_settings()
    base = s.aipp_backend_public_url.rstrip("/")
    return f"{base}/api/auth/oidc/callback"


async def _fetch_metadata(discovery_url: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(discovery_url)
        r.raise_for_status()
        return r.json()


def _mint_state(provider_id: str) -> str:
    """Generate a state token, remember which provider issued it, and
    garbage-collect expired ones."""
    now = time.time()
    for k, (_pid, exp) in list(_STATE_STORE.items()):
        if exp < now:
            _STATE_STORE.pop(k, None)
    state = secrets.token_urlsafe(24)
    _STATE_STORE[state] = (provider_id, now + _STATE_TTL_SECONDS)
    return state


def _consume_state(state: str) -> Optional[str]:
    """Return the provider_id that minted this state, or None if invalid."""
    entry = _STATE_STORE.pop(state, None)
    if entry is None:
        return None
    pid, exp = entry
    return pid if exp > time.time() else None


async def build_authorization_url(provider_id: Optional[str] = None) -> str:
    cfg = await resolve_provider(provider_id)
    meta = await _fetch_metadata(cfg.discovery_url)
    auth_ep = meta["authorization_endpoint"]
    state = _mint_state(cfg.provider_id)
    from urllib.parse import urlencode
    qs = urlencode({
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(),
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    })
    return f"{auth_ep}?{qs}"


async def exchange_code(code: str, state: str) -> dict:
    """Trade the auth-code for tokens; return normalised user info."""
    provider_id = _consume_state(state)
    if provider_id is None:
        raise OIDCError("state_invalid_or_expired")
    cfg = await resolve_provider(provider_id)

    meta = await _fetch_metadata(cfg.discovery_url)
    async with httpx.AsyncClient(timeout=10.0) as c:
        tok = await c.post(
            meta["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(),
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
            },
        )
        if tok.status_code >= 300:
            logger.warning("oidc.exchange: token endpoint %s → %s %s",
                           meta["token_endpoint"], tok.status_code, tok.text[:200])
            raise OIDCError(f"token_exchange_failed_{tok.status_code}")
        tokens = tok.json()
        access = tokens.get("access_token")
        if not access:
            raise OIDCError("token_response_missing_access_token")

        ui = await c.get(
            meta["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access}"},
        )
        if ui.status_code >= 300:
            raise OIDCError(f"userinfo_failed_{ui.status_code}")
        info = ui.json()

    return {
        "email": (info.get("email") or "").strip().lower(),
        "email_verified": bool(info.get("email_verified", True)),
        "name": info.get("name") or info.get("preferred_username") or "",
        "sub": info.get("sub"),
        "provider": cfg.kind,
        "provider_id": cfg.provider_id,
    }
