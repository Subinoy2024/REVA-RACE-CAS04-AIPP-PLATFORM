"""Enterprise SSO admin API — configure Entra ID / Google / OIDC at runtime.

Iteration-26.6.

Auth model:
  * All endpoints require a valid admin JWT (see `services/auth_service`).
  * Client secrets are Fernet-encrypted at rest and NEVER returned.
  * Env-configured OIDC (`OIDC_PROVIDER` in .env) still works — the
    `/api/auth/oidc/status` endpoint keeps advertising it. Providers added
    here are surfaced ADDITIONALLY on the login page via
    `/api/auth/identity-providers/public`.

Discovery URL defaults for the well-known providers:
  * Entra ID  → `https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration`
  * Google    → `https://accounts.google.com/.well-known/openid-configuration`
  * OIDC      → user provides.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import AIPPError
from backend.database.connection import get_session, session_scope
from backend.database.models import IdentityProvider
from backend.services.auth_service import get_current_user
from backend.services.crypto_service import decrypt, encrypt


router = APIRouter(prefix="/api/auth/identity-providers", tags=["auth"])


VALID_KINDS = {"entra", "google", "oidc"}


class IdentityProviderCreate(BaseModel):
    kind: str = Field(..., description="`entra` | `google` | `oidc`")
    display_name: str = Field(..., min_length=1, max_length=120)
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    discovery_url: Optional[str] = None
    tenant_id: Optional[str] = None
    enabled: bool = True


class IdentityProviderOut(BaseModel):
    id: str
    kind: str
    display_name: str
    client_id: str
    discovery_url: Optional[str]
    tenant_id: Optional[str]
    enabled: bool


class PublicIdentityProvider(BaseModel):
    """Everything the (unauthenticated) login page needs — no secrets."""
    id: str
    kind: str
    display_name: str


def _autoderive_discovery_url(kind: str, tenant_id: Optional[str]) -> Optional[str]:
    if kind == "entra":
        t = tenant_id or "common"
        return f"https://login.microsoftonline.com/{t}/v2.0/.well-known/openid-configuration"
    if kind == "google":
        return "https://accounts.google.com/.well-known/openid-configuration"
    return None


@router.get("", response_model=list[IdentityProviderOut])
async def list_providers(
    sess: AsyncSession = Depends(get_session),
    _admin=Depends(get_current_user),
) -> list[IdentityProviderOut]:
    rows = (await sess.execute(select(IdentityProvider))).scalars().all()
    return [IdentityProviderOut(
        id=str(r.id),
        kind=r.kind,
        display_name=r.display_name,
        client_id=r.client_id,
        discovery_url=r.discovery_url,
        tenant_id=r.tenant_id,
        enabled=r.enabled,
    ) for r in rows]


@router.post("", response_model=IdentityProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: IdentityProviderCreate,
    _admin=Depends(get_current_user),
) -> IdentityProviderOut:
    if body.kind not in VALID_KINDS:
        raise HTTPException(400, f"Unknown kind: {body.kind}. Use one of {sorted(VALID_KINDS)}")
    if not body.discovery_url:
        body.discovery_url = _autoderive_discovery_url(body.kind, body.tenant_id)
    if not body.discovery_url:
        raise HTTPException(400, "`discovery_url` is required for kind=oidc")
    try:
        enc = encrypt(body.client_secret)
    except AIPPError as e:
        raise HTTPException(500, f"Cannot encrypt secret: {e}")
    async with session_scope() as sess:
        row = IdentityProvider(
            kind=body.kind,
            display_name=body.display_name,
            client_id=body.client_id,
            client_secret_enc=enc,
            discovery_url=body.discovery_url,
            tenant_id=body.tenant_id,
            enabled=body.enabled,
        )
        sess.add(row)
        await sess.flush()
        return IdentityProviderOut(
            id=str(row.id),
            kind=row.kind,
            display_name=row.display_name,
            client_id=row.client_id,
            discovery_url=row.discovery_url,
            tenant_id=row.tenant_id,
            enabled=row.enabled,
        )


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: str,
    _admin=Depends(get_current_user),
) -> dict:
    async with session_scope() as sess:
        row = await sess.get(IdentityProvider, provider_id)
        if row is None:
            raise HTTPException(404, "Provider not found")
        await sess.delete(row)
    return {"deleted": True, "id": provider_id}


@router.get("/public", response_model=list[PublicIdentityProvider])
async def list_public_providers(
    sess: AsyncSession = Depends(get_session),
) -> list[PublicIdentityProvider]:
    """Unauthenticated. Used by the login page to render 'Sign in with X' buttons."""
    rows = (await sess.execute(
        select(IdentityProvider).where(IdentityProvider.enabled == True)  # noqa: E712
    )).scalars().all()
    return [PublicIdentityProvider(
        id=str(r.id),
        kind=r.kind,
        display_name=r.display_name,
    ) for r in rows]
