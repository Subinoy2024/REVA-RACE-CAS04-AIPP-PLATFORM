"""Slack Interactive Endpoints — HITL button click bridge.

Why this exists
---------------
n8n's Wait node (resume: webhook) parks a workflow and exposes a signed
resume URL via `$execution.resumeUrl`. Historically we posted that URL
to Slack as two plain hyperlinks — click "Approve" → GET request → n8n
resumes. That works but looks amateur next to a native Slack Block Kit
message with real Approve / Reject buttons.

Slack "interactivity" fires a POST to a URL you configure in the app
manifest when a user clicks a button. The payload is
`application/x-www-form-urlencoded` with a single `payload=` field
containing a JSON string that includes:

  * `actions[0].action_id`  →  "approve"  or  "reject"
  * `actions[0].value`      →  the n8n resume URL (we stuff it there)
  * `user`, `channel`, `response_url`, plus a signature timestamp header

This endpoint:
  1. Verifies `X-Slack-Signature` (HMAC-SHA256 over `v0:{ts}:{raw_body}`)
  2. Extracts the decision + resume URL
  3. Forwards to n8n so the parked execution resumes with `?a=approve|reject`
  4. Persists the decision to the `audit_logs` table with action
     `slack.hitl.decision` so the "Approvals" Gradio tab can render a
     full compliance-friendly history of who signed off on what.
  5. Returns a `response_action: update` payload so Slack immediately
     replaces the message with an audit-friendly "✅ Approved by @user"
     card — no jarring "actions faded out" state.

Endpoints
---------
POST /api/slack/interactions   (URL configured in Slack app manifest)
GET  /api/slack/approvals      (Gradio "Approvals" tab reads this)

Env vars
--------
SLACK_SIGNING_SECRET  — required. Copy from Slack app → Basic Information.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import urllib.parse
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.services.audit_service import AuditService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/slack", tags=["slack"])
_audit = AuditService()

# Slack drops requests older than 5 minutes — mirror that so a replayed
# click can't resume an execution long after the window has closed.
_MAX_SLACK_SKEW_SECONDS = 300

# Audit action tag — kept as a single constant so the /approvals endpoint
# and any future consumer stay in lock-step.
HITL_AUDIT_ACTION = "slack.hitl.decision"


def _verify_slack_signature(
    signing_secret: str,
    raw_body: bytes,
    timestamp: str | None,
    signature: str | None,
) -> None:
    """Validate `X-Slack-Signature` — raises HTTPException on failure.

    Slack spec: base = "v0:{timestamp}:{raw_body}", HMAC-SHA256 keyed
    with the signing secret, hex-encoded, prefixed with "v0=".
    """
    if not signing_secret:
        # Fail loud in production — never silently accept an unsigned click.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SLACK_SIGNING_SECRET is not configured on the AIPP backend",
        )
    if not timestamp or not signature:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "missing X-Slack-Request-Timestamp or X-Slack-Signature header",
        )
    try:
        ts_int = int(timestamp)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "malformed timestamp")
    if abs(time.time() - ts_int) > _MAX_SLACK_SKEW_SECONDS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "stale request (replay?)")

    base = b"v0:" + timestamp.encode() + b":" + raw_body
    expected = "v0=" + hmac.new(
        signing_secret.encode(), base, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad signature")


def _decode_payload(raw_body: bytes) -> dict[str, Any]:
    """Slack posts `payload=<url-encoded JSON>` — unwrap it."""
    parsed = urllib.parse.parse_qs(raw_body.decode(errors="replace"))
    payload_list = parsed.get("payload") or []
    if not payload_list:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "missing payload field in Slack form body")
    try:
        return json.loads(payload_list[0])
    except json.JSONDecodeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"payload is not valid JSON: {e}")


async def _resume_n8n_execution(resume_url: str, decision: str) -> tuple[int, str]:
    """Fire the resume URL with ?a=approve|reject.

    Slack's Cloudflare front-door blocks default python-requests / httpx
    user agents; use a browser-shaped UA that mirrors what the deploy /
    hitl_demo scripts already use.
    """
    sep = "&" if "?" in resume_url else "?"
    final_url = f"{resume_url}{sep}a={decision}"
    ua = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 AIPP-Slack-Bridge"
    )
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        r = await client.get(final_url, headers={"User-Agent": ua})
        return r.status_code, r.text[:280]


def _summary_card(decision: str, user: str, workflow_hint: str) -> dict:
    """Return a Block Kit payload that overwrites the original approval
    card with an audit-trail-friendly "sealed" version.
    """
    emoji = "✅" if decision == "approve" else "❌"
    verb = "Approved" if decision == "approve" else "Rejected"
    return {
        "response_action": "update",
        "replace_original": True,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{emoji} *{verb} by <@{user}>*\n"
                        f"_{workflow_hint}_\n"
                        f"_At {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}_"
                    ),
                },
            },
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": (
                        "Sealed via AIPP Slack bridge · signature verified · "
                        "n8n execution resumed."
                    ),
                }],
            },
        ],
    }


@router.post("/interactions")
async def slack_interactions(
    request: Request,
    x_slack_signature: str | None = Header(default=None,
                                            alias="X-Slack-Signature"),
    x_slack_request_timestamp: str | None = Header(default=None,
                                                    alias="X-Slack-Request-Timestamp"),
) -> dict:
    """Bridge Slack Block Kit button clicks into n8n resume-webhook calls.

    Slack expects a 200 response within 3 seconds and treats a JSON body
    of `{response_action: update, blocks: [...]}` as an instruction to
    replace the original message. We do the resume call synchronously
    because n8n resumes are fast (< 1s) — no need for the "return 200
    now, work in the background" pattern.
    """
    settings = get_settings()
    raw = await request.body()
    _verify_slack_signature(
        settings.slack_signing_secret, raw,
        x_slack_request_timestamp, x_slack_signature,
    )
    payload = _decode_payload(raw)

    actions = payload.get("actions") or []
    if not actions:
        # Slack also uses this endpoint for `block_suggestion`, `view_submission`,
        # etc. — none of those apply to our HITL flow, so accept + ack.
        logger.info("slack_interactions: non-action payload type=%s ignored",
                    payload.get("type"))
        return {"ok": True, "ignored": True, "type": payload.get("type")}

    action = actions[0]
    action_id = (action.get("action_id") or "").lower()
    resume_url = action.get("value") or ""
    user = (payload.get("user") or {}).get("username") or "unknown"

    if action_id not in ("approve", "reject"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"unknown action_id {action_id!r} — expected approve|reject")
    if not resume_url or "webhook-waiting" not in resume_url:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "button `value` must carry the n8n resume URL "
            "(should contain 'webhook-waiting')",
        )

    try:
        status_code, body = await _resume_n8n_execution(resume_url, action_id)
    except Exception as e:                                          # noqa: BLE001
        logger.exception("slack_interactions: n8n resume failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"n8n resume call failed: {e}")

    # Extract the n8n execution ID from the resume URL — the "Approvals"
    # tab shows it so operators can jump straight to the run graph.
    exec_id_match = re.search(r"/webhook-waiting/(\d+)", resume_url)
    exec_id = exec_id_match.group(1) if exec_id_match else None
    workflow_hint = ((payload.get("message") or {}).get("text") or "")[:120]
    user_id = (payload.get("user") or {}).get("id") or ""
    channel_name = (payload.get("channel") or {}).get("name") or ""

    # Best-effort audit write — never fail the Slack ack if DB is briefly
    # unavailable (Slack will retry the request and duplicate the audit
    # row otherwise, which is confusing).
    try:
        await _audit.log(
            action=HITL_AUDIT_ACTION,
            actor=user,
            tool="slack",
            details={
                "decision": action_id,
                "slack_user": user,
                "slack_user_id": user_id,
                "slack_channel": channel_name,
                "n8n_execution_id": exec_id,
                "n8n_resume_status": status_code,
                "workflow_hint": workflow_hint,
                # Do NOT persist the raw resume URL — it contains a
                # short-lived signed token that grants execution resume.
            },
        )
    except Exception as e:                                          # noqa: BLE001
        logger.warning("slack_interactions: audit write failed: %s", e)

    logger.info(
        "slack_interactions: user=%s decision=%s n8n_status=%s exec=%s",
        user, action_id, status_code, exec_id,
    )

    # Best-effort: give Slack a nice "sealed" replacement message.
    return _summary_card(action_id, user, workflow_hint)


@router.get("/approvals")
async def list_approvals(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Return the last N HITL decisions for the Approvals Gradio tab.

    Reads from `audit_logs WHERE action='slack.hitl.decision'` and
    surfaces a flat, UI-friendly shape:

        {
          "total": 42,
          "approvals": [
            {
              "id": "<uuid>",
              "when": "<iso ts>",
              "decision": "approve" | "reject",
              "user": "<slack username>",
              "user_id": "<slack user id>",
              "channel": "<channel name>",
              "workflow_hint": "<short line from the Slack card>",
              "n8n_execution_id": "<int-as-str>",
              "n8n_status": <int>
            }
          ]
        }

    Filtering + sorting happens client-side in the Gradio tab; the API
    just streams the raw rows.
    """
    from sqlalchemy import select

    from backend.database.connection import session_scope
    from backend.database.models import AuditLog

    async with session_scope() as sess:
        rows = (
            await sess.execute(
                select(AuditLog)
                .where(AuditLog.action == HITL_AUDIT_ACTION)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    approvals = []
    for r in rows:
        details = r.details_json or {}
        approvals.append({
            "id": str(r.id),
            "when": r.created_at.isoformat(),
            "decision": details.get("decision", "?"),
            "user": details.get("slack_user") or r.actor or "?",
            "user_id": details.get("slack_user_id", ""),
            "channel": details.get("slack_channel", ""),
            "workflow_hint": details.get("workflow_hint", ""),
            "n8n_execution_id": details.get("n8n_execution_id"),
            "n8n_status": details.get("n8n_resume_status"),
        })
    return {"total": len(approvals), "approvals": approvals}


@router.get("/health")
async def slack_health() -> dict:
    """Cheap probe used during app-manifest setup to sanity-check the URL."""
    settings = get_settings()
    return {
        "ok": True,
        "signing_secret_configured": bool(settings.slack_signing_secret),
    }
