"""Transactional email via Resend (used for password-reset).

Design:
  * Resend HTTP API — `POST https://api.resend.com/emails` with
    `Authorization: Bearer <key>`. No SDK needed; `httpx` is already
    pinned.
  * If `RESEND_API_KEY` is empty, we run in **dev fallback mode**: the
    email body is logged to stdout so the operator can copy the reset
    URL from the container logs. Real emails are only sent when the key
    is set — a thesis-appropriate "graceful degradation" pattern.
  * Fire-and-forget: the caller awaits the send but network errors are
    swallowed and logged; we never fail the surrounding request because
    the mail provider had a hiccup.
"""

from __future__ import annotations

import httpx

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


async def send_email(*, to: str, subject: str, html: str, text: str) -> dict:
    """Send an email. Returns `{"sent": bool, "reason": str}`.

    Never raises — email is a side-effect, not a critical path.
    """
    s = get_settings()
    key = s.resend_api_key.strip()
    if not key:
        # Dev fallback — dump to logs so the operator can act.
        logger.warning(
            "email.send: RESEND_API_KEY not set — DEV MODE. Would send:\n"
            "  To      : %s\n  Subject : %s\n  Text    : %s",
            to, subject, text,
        )
        return {"sent": False, "reason": "resend_not_configured"}

    payload = {
        "from": s.email_from,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json=payload,
            )
            if r.status_code >= 300:
                logger.warning("email.send: Resend rejected %s → %s %s",
                               to, r.status_code, r.text[:200])
                return {"sent": False, "reason": f"http_{r.status_code}"}
            return {"sent": True, "reason": "ok"}
    except Exception as e:  # noqa: BLE001
        logger.warning("email.send: exception sending to %s: %s", to, e)
        return {"sent": False, "reason": "network_error"}
