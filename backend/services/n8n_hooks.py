"""AIPP → n8n webhook dispatcher.

Iteration-28 companion to the 15 n8n workflows in `/app/n8n/workflows/`.

Purpose
-------
A minimal helper that lets AIPP backend services POST to n8n webhook
triggers so the two systems are coupled at runtime, not just at
config-time. Called from:

  * `services/pipeline_service.py` — after a successful generation, fire
    workflow #11 (SOP Generator) if the run had an RCA report attached.
  * `api/pipelines.py`             — on RCA endpoint, fire #10 (Incident
    Commander) for high-severity findings.
  * `services/deploy_service.py`   — after auto-deploy, fire #05
    (Pipeline Status Digest) refresh.

Environment
-----------
  N8N_BASE_URL   — reused from existing config
  N8N_API_KEY    — reused; sent as X-N8N-API-KEY header for authenticated
                   webhook endpoints. Public webhooks ignore it.

All calls are best-effort — failures are logged but do NOT block the
caller. n8n outage must never break AIPP's generation flow.
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


# Map of AIPP-side event → n8n webhook path (matches build_workflows.py)
_EVENT_ROUTES: dict[str, str] = {
    "sub_vending":       "/webhook/aipp-sub-vending",
    "troubleshoot":      "/webhook/aipp-troubleshoot",
    "grafana_alert":     "/webhook/aipp-grafana",
    "incident":          "/webhook/aipp-incident",
    "sop":               "/webhook/aipp-sop",
    "pipeline_review":   "/webhook/aipp-pipeline-review",  # HITL gate (#16)
    "iac_drift":         "/webhook/aipp-iac-drift",        # legacy — resolves at n8n side
}


async def fire(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fire the n8n webhook mapped to `event` with the given payload.

    Returns the n8n response (or an ``{"ok": False, "error": ...}``
    envelope if n8n was unreachable). Never raises — failures are
    logged and swallowed so the caller's transaction can commit.

    Parameters
    ----------
    event
        Key from `_EVENT_ROUTES`. Unknown events log a warning and
        return `{"ok": False, "error": "unknown_event"}`.
    payload
        JSON-serialisable dict passed as the webhook body. Every
        workflow expects a `body` wrapper — n8n's `webhook` node
        unwraps it automatically in expression context.
    """
    if event not in _EVENT_ROUTES:
        logger.warning("n8n_hooks: unknown event %r", event)
        return {"ok": False, "error": "unknown_event"}

    s = get_settings()
    base = (s.n8n_base_url or "").rstrip("/")
    if not base:
        # Silent no-op when n8n isn't configured — AIPP works standalone.
        return {"ok": False, "error": "n8n_not_configured"}

    url = f"{base}{_EVENT_ROUTES[event]}"
    headers = {"Content-Type": "application/json"}
    if s.n8n_api_key:
        headers["X-N8N-API-KEY"] = s.n8n_api_key

    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(url, json=payload, headers=headers)
            logger.info("n8n_hooks: event=%s → %s %s", event, r.status_code,
                        (r.text or "")[:120])
            return {
                "ok": 200 <= r.status_code < 300,
                "status_code": r.status_code,
                "response": (r.text or "")[:500],
            }
    except Exception as e:                                       # noqa: BLE001
        logger.warning("n8n_hooks: event=%s failed: %s", event, e)
        return {"ok": False, "error": str(e)}
