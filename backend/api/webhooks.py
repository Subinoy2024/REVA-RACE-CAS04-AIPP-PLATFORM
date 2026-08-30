"""Inbound alert bridges — Grafana + Azure Monitor → AIPP → n8n.

Iteration-33 companion to `services/n8n_hooks.py`.

Why this exists
---------------
Real production alerts don't come through the Gradio UI. They arrive
from Grafana Contact Points and Azure Monitor Action Groups. Both
platforms POST arbitrary JSON to a URL you configure.

This module gives them a URL each — validates and normalises the
payload, records an entry in `agent_traces` for full audit, then
forwards to the right n8n workflow (#08 for Grafana, #10 for Azure).

Endpoints
---------
POST /api/webhooks/grafana        — accepts Grafana webhook payload
POST /api/webhooks/azure-monitor  — accepts Azure Monitor common schema

Auth
----
Both endpoints require `Authorization: Bearer <PROXY_API_KEY>`. Same
key as the /api/proxy/* router — rotating one rotates the other.
"""
from __future__ import annotations

import hmac
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, status

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.services.n8n_hooks import fire

logger = get_logger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _require_api_key(authorization: Optional[str]) -> None:
    settings = get_settings()
    if not settings.proxy_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "proxy_api_key not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    presented = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(presented, settings.proxy_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid api key")


# ---------------------------------------------------------------------------
@router.post("/grafana")
async def grafana_alert(
    payload: dict[str, Any] = Body(...),
    authorization: Optional[str] = Header(None),
) -> dict:
    """Grafana Contact Point → n8n workflow #08.

    Grafana sends `{alerts:[{status, labels:{alertname, severity, instance}, ...}]}`
    We normalise a subset then forward. n8n's Extract Alert node already
    understands both this shape and the Azure shape.
    """
    _require_api_key(authorization)
    alerts = payload.get("alerts", [])
    normalised = {
        "source": "grafana",
        "alert_count": len(alerts),
        "commonLabels": payload.get("commonLabels") or (
            alerts[0].get("labels", {}) if alerts else {}
        ),
        "commonAnnotations": payload.get("commonAnnotations") or (
            alerts[0].get("annotations", {}) if alerts else {}
        ),
        "alerts": alerts,
    }
    logger.info("grafana_alert: %d alert(s) received, forwarding to n8n #08",
                len(alerts))
    n8n_resp = await fire("grafana_alert", {"body": normalised})
    return {"ok": True, "forwarded": True, "n8n": n8n_resp}


# ---------------------------------------------------------------------------
@router.post("/azure-monitor")
async def azure_monitor_alert(
    payload: dict[str, Any] = Body(...),
    authorization: Optional[str] = Header(None),
) -> dict:
    """Azure Monitor Action Group → n8n workflow #10 (Incident Commander).

    Azure sends the "Common Alert Schema":
      { schemaId, data: { essentials: {alertRule, severity, ...}, alertContext } }
    """
    _require_api_key(authorization)
    essentials = (payload.get("data", {}) or {}).get("essentials", {}) or {}
    logger.info("azure_monitor_alert: rule=%s severity=%s",
                essentials.get("alertRule"), essentials.get("severity"))
    n8n_resp = await fire("incident", {"body": payload})
    return {"ok": True, "forwarded": True, "n8n": n8n_resp}


# ---------------------------------------------------------------------------
@router.get("/health")
async def health(authorization: Optional[str] = Header(None)) -> dict:
    """Cheap probe — used by Grafana/Azure to test the URL during setup."""
    _require_api_key(authorization)
    return {"ok": True, "handlers": ["grafana", "azure-monitor"]}
