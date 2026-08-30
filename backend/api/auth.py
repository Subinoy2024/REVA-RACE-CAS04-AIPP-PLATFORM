"""Authentication endpoints — login, /me, logout, OIDC, password reset,
and brute-force protection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from backend.core.brute_force import (
    email_lockout,
    enforce_email_not_locked,
    login_ip_limiter,
)
from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.core.rate_limit import _client_key
from backend.services import oidc_service
from backend.services.auth_service import (
    authenticate,
    create_access_token,
    create_reset_token,
    decode_reset_token,
    disable_default_account_on_oidc,
    get_current_user,
    update_password,
    upsert_user_from_oidc,
)
from backend.services.email_service import send_email

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = get_logger(__name__)


# --- Login / me / logout ----------------------------------------------------
class LoginRequest(BaseModel):
    # Not EmailStr — `EmailStr` rejects `.local` TLDs which is exactly
    # what our seeded default admin uses. Server-side we normalise
    # `email` to lower-case in `authenticate()`.
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1)


@router.post("/login")
async def login(body: LoginRequest, request: Request) -> dict:
    """Return a JWT access token on valid credentials.

    Brute-force protection:
      * IP-level rate limit: 10 attempts / 60 s (RateLimiter)
      * Email-level lockout: 5 failures → 15 min lock
      * Successful login clears the email counter.
    """
    login_ip_limiter.check(_client_key(request))
    email = body.email.strip().lower()
    enforce_email_not_locked(email)
    try:
        result = await authenticate(email, body.password)
    except HTTPException as e:
        if e.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            email_lockout.record_failure(email)
        raise
    email_lockout.record_success(email)
    return result


@router.get("/me")
async def me(current: dict = Depends(get_current_user)) -> dict:
    return current


@router.post("/logout")
async def logout(current: dict = Depends(get_current_user)) -> dict:
    """Logout is client-side (drop the token). This endpoint just confirms
    the token was valid at the moment of the call."""
    return {"ok": True, "message": f"Bye, {current['email']}"}


# --- OIDC (Google / Azure AD) ------------------------------------------------
@router.get("/oidc/status")
async def oidc_status() -> dict:
    return oidc_service.status_dict()


@router.get("/oidc/login")
async def oidc_login(provider_id: str | None = None):
    """302 → provider authorization URL.

    `provider_id`:
      * omitted / "env" → legacy .env-driven provider
      * UUID            → row from the `identity_providers` table
    """
    try:
        url = await oidc_service.build_authorization_url(provider_id=provider_id)
    except oidc_service.OIDCNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))
    return RedirectResponse(url, status_code=302)


@router.get("/oidc/callback")
async def oidc_callback(code: str, state: str):
    """Exchange the auth-code for tokens, upsert the user, mint an AIPP
    JWT, and redirect the browser back to the Gradio UI with the JWT
    baked into `?token=…`.

    Gradio's startup reads the query param on the very first request and
    auto-logs the user in — no manual copy-paste.
    """
    try:
        info = await oidc_service.exchange_code(code, state)
    except (oidc_service.OIDCNotConfigured, oidc_service.OIDCError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not info["email"] or not info["email_verified"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="OIDC user has no verified email")
    user = await upsert_user_from_oidc(email=info["email"], name=info["name"] or "")
    token = create_access_token(user_id=str(user.id), email=user.email)
    ui_url = get_settings().aipp_public_url.rstrip("/")
    return RedirectResponse(f"{ui_url}/?token={token}&email={user.email}", status_code=302)


@router.post("/oidc/enable")
async def enable_oidc(current: dict = Depends(get_current_user)) -> dict:
    """Admin action — freezes the default seeded admin so its password
    is dead after cloud identity is live. Idempotent."""
    if current.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return await disable_default_account_on_oidc()


# --- Password reset ---------------------------------------------------------
class PasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=200)


@router.post("/password/request")
async def request_password_reset(body: PasswordResetRequest, request: Request) -> dict:
    """Send a signed reset link to the user's email. Silent on unknown
    users (no enumeration). Uses Resend if configured, otherwise dumps
    the link to server logs (dev mode)."""
    login_ip_limiter.check(_client_key(request))
    email = body.email.strip().lower()

    # Look up the user; if missing, still return 200 so we don't leak.
    from backend.database.connection import session_scope
    from backend.database.models import User
    from sqlalchemy import select
    async with session_scope() as sess:
        user = (await sess.execute(select(User).where(User.email == email))).scalar_one_or_none()

    if user is not None and user.is_active:
        token = create_reset_token(user_id=str(user.id), email=user.email)
        s = get_settings()
        link = f"{s.aipp_public_url.rstrip('/')}/?reset={token}"
        subject = "Reset your AIPP password"
        text = (
            f"Hi,\n\nSomeone (hopefully you) asked to reset the password "
            f"for {user.email}. Follow the link below within 1 hour:\n\n"
            f"{link}\n\nIf this wasn't you, ignore this email — nothing changes.\n"
        )
        html = (
            f"<p>Hi,</p>"
            f"<p>Reset your AIPP password using the link below (valid for 1 hour):</p>"
            f"<p><a href=\"{link}\">Reset password</a></p>"
            f"<p>If this wasn't you, ignore this email.</p>"
        )
        await send_email(to=user.email, subject=subject, html=html, text=text)
    return {"ok": True, "message": "If the email is known, a reset link has been sent."}


@router.post("/password/reset")
async def confirm_password_reset(body: PasswordResetConfirm) -> dict:
    """Verify the signed reset token and update the password."""
    import jwt as _jwt
    try:
        payload = decode_reset_token(body.token)
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset link expired")
    except _jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset link")
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token payload")
    await update_password(email=email, new_password=body.new_password)
    email_lockout.reset(email)     # clear any pending lock
    return {"ok": True, "message": "Password updated."}
