"""Authentication service — bcrypt password hashing + JWT tokens + admin seeding.

Design notes (adapted from the integration playbook to our stack):
  * The playbook assumed MongoDB + React with httpOnly cookies. We use
    Postgres + Gradio, where the "frontend" is server-side Python — so we
    switched to `Authorization: Bearer <jwt>` header transport. The
    session token lives in Gradio's `gr.State`, never in the browser DOM.
  * `create_all()` handles table creation; `seed_default_admin()` fills
    the users table on first boot. Idempotent — safe across restarts.
  * When the admin `.env` password is rotated, the hash is updated so
    the operator can never be locked out of their own instance.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.database.connection import get_session, session_scope
from backend.database.models import User

logger = get_logger(__name__)

JWT_ALGORITHM = "HS256"


def create_reset_token(*, user_id: str, email: str) -> str:
    """Short-lived JWT used by the password-reset flow."""
    s = get_settings()
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "type": "reset",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_reset_token(token: str) -> dict:
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "reset":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


async def upsert_user_from_oidc(*, email: str, name: str) -> "User":
    """Ensure a `users` row exists for an OIDC identity. Never sets a
    password hash — the row is `password_hash="!oidc!"` (unusable via
    bcrypt.checkpw) so the local login flow can never authenticate
    against an OIDC-provisioned account.

    Also flips every `is_default=true` seeded admin to `is_active=false`
    the first time an OIDC user logs in — the same policy `oidc/enable`
    enforces manually.
    """
    from backend.database.models import User
    async with session_scope() as sess:
        u = (await sess.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if u is None:
            u = User(
                email=email,
                password_hash="!oidc!",
                name=name or None,
                role="admin",
                is_active=True,
                is_default=False,
            )
            sess.add(u)
            await sess.flush()
        else:
            if name and not u.name:
                u.name = name
            if not u.is_active:
                # OIDC users are always allowed unless an admin disabled them explicitly.
                # (The default seeded admin is a *different* row.)
                pass
        # Deactivate seeded defaults
        for d in (await sess.execute(select(User).where(User.is_default == True))).scalars():  # noqa: E712
            if d.email != email and d.is_active:
                d.is_active = False
        # Refresh to make sure we return a persistent row
        return u


async def update_password(*, email: str, new_password: str) -> None:
    from backend.database.models import User
    async with session_scope() as sess:
        u = (await sess.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if u is None:
            # Silent — do not reveal enumeration.
            return
        u.password_hash = hash_password(new_password)


# ---- Password hashing -------------------------------------------------------
def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---- JWT --------------------------------------------------------------------
def create_access_token(*, user_id: str, email: str) -> str:
    s = get_settings()
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=s.jwt_access_ttl_minutes),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])


# ---- Dependency: current user ----------------------------------------------
async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    sess: AsyncSession = Depends(get_session),
) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("sub")
    user = (await sess.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "is_default": user.is_default,
    }


# ---- Login / logout core logic ---------------------------------------------
async def authenticate(email: str, password: str) -> dict:
    """Return the JWT + minimal user info on success. Raise 401 on failure."""
    async with session_scope() as sess:
        user = (await sess.execute(
            select(User).where(User.email == email.strip().lower())
        )).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Account is disabled (cloud identity is active)")
        token = create_access_token(user_id=str(user.id), email=user.email)
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "is_default": user.is_default,
            },
        }


# ---- Admin seeding + OIDC toggle -------------------------------------------
async def seed_default_admin() -> None:
    """Idempotently ensure the default admin exists.

    - If missing → create with the .env password (bcrypt-hashed).
    - If present and .env password rotated → update hash.
    - Never touches `is_active` — that flag is owned by the OIDC toggle.
    """
    s = get_settings()
    email = s.admin_email.strip().lower()
    async with session_scope() as sess:
        existing = (await sess.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is None:
            sess.add(User(
                email=email,
                password_hash=hash_password(s.admin_password),
                name="Default Admin",
                role="admin",
                is_active=True,
                is_default=True,
            ))
            logger.info("auth.seed: created default admin %s", email)
        else:
            if not verify_password(s.admin_password, existing.password_hash):
                existing.password_hash = hash_password(s.admin_password)
                logger.info("auth.seed: rotated default admin password for %s", email)


async def disable_default_account_on_oidc() -> dict:
    """Called by `POST /api/auth/oidc/enable`. Flips the default account
    to `is_active=false` so nobody can use the seeded password after the
    org's identity provider takes over.

    Full OIDC provider integration (Google / Azure AD / Okta) is
    intentionally out of scope for this iteration — the DB flag is the
    "hard" part of the story. Wiring an OIDC redirect flow can be added
    behind the same endpoint later without breaking any caller.
    """
    async with session_scope() as sess:
        result = await sess.execute(select(User).where(User.is_default == True))     # noqa: E712
        rows = result.scalars().all()
        touched = []
        for u in rows:
            if u.is_active:
                u.is_active = False
                touched.append(u.email)
        return {"disabled_accounts": touched, "count": len(touched)}
