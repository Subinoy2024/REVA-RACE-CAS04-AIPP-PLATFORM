"""n8n MCP adapter — talks to a real n8n REST API. Returns clear
`configured=False` responses when the user hasn't provided base URL + API key
(no mock data ever)."""

from __future__ import annotations

from typing import Any, List, Optional

import httpx

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class N8nAdapter(BaseMCPAdapter):
    name = "n8n"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.n8n_base_url and s.n8n_api_key)

    def _register_tools(self) -> None:
        self._register("list_workflows", self._list_workflows)
        self._register("get_executions", self._get_executions)
        # Write actions — added iteration-20 for AIPP → n8n triggering.
        self._register("execute_workflow", self._execute_workflow)
        self._register("activate_workflow", self._activate_workflow)
        self._register("deactivate_workflow", self._deactivate_workflow)
        self._register("ping", self._ping)

    def _headers(self) -> dict:
        # Real browser UA — some n8n deployments sit behind Cloudflare which
        # blocks default httpx UA with error 1010 (Bot Fight Mode).
        return {
            "X-N8N-API-KEY": get_settings().n8n_api_key or "",
            "Accept": "application/json",
            "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
                           "AIPP-Backend"),
        }

    async def _list_workflows(self) -> List[dict]:
        s = get_settings()
        async with httpx.AsyncClient(base_url=s.n8n_base_url or "", timeout=20.0) as c:
            r = await c.get("/api/v1/workflows", headers=self._headers())
            r.raise_for_status()
            payload = r.json()
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    async def _get_executions(self, *, workflow_id: Optional[str] = None, limit: int = 5) -> List[dict]:
        s = get_settings()
        params: dict[str, Any] = {"limit": limit}
        if workflow_id:
            params["workflowId"] = workflow_id
        async with httpx.AsyncClient(base_url=s.n8n_base_url or "", timeout=20.0) as c:
            r = await c.get("/api/v1/executions", headers=self._headers(), params=params)
            r.raise_for_status()
            payload = r.json()
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    # ------------------------------------------------------------------
    # Write actions (iteration-20)
    # ------------------------------------------------------------------
    async def _execute_workflow(
        self,
        *,
        workflow_id: str,
        input_data: Optional[dict] = None,
    ) -> dict:
        """Kick off a workflow run.

        n8n's Public API (`/api/v1/*`) does NOT expose an execute endpoint
        (that's only on the internal `/rest/*` used by the editor UI, which
        returns 405 to external callers). Instead, we introspect the
        workflow's trigger node and invoke it the right way:

          • webhook trigger  → POST the workflow's webhook URL
          • form  trigger    → same as webhook (form URL)
          • schedule / cron  → cannot trigger on-demand; return a helpful hint
          • manual / other   → return a helpful hint

        Returns { ok, kind, response? , webhook_url? , message? } so the UI
        can render the outcome cleanly.
        """
        s = get_settings()
        base = (s.n8n_base_url or "").rstrip("/")
        headers = self._headers()

        async with httpx.AsyncClient(base_url=base, timeout=30.0) as c:
            # 1. Fetch the workflow definition to inspect the trigger node.
            r = await c.get(f"/api/v1/workflows/{workflow_id}", headers=headers)
            r.raise_for_status()
            wf = r.json()

            # 2. Find the first webhook / form trigger; else fall back.
            trigger = None
            for node in wf.get("nodes", []):
                if node.get("type") in (
                    "n8n-nodes-base.webhook",
                    "n8n-nodes-base.formTrigger",
                ):
                    trigger = node
                    break

            if trigger is None:
                # Schedule/error/manual — no HTTP entrypoint.
                trig_types = sorted({n.get("type", "") for n in wf.get("nodes", [])
                                     if "trigger" in n.get("type", "").lower()
                                     or n.get("type", "").endswith(".webhook")})
                return {
                    "ok": False,
                    "kind": "unsupported_trigger",
                    "trigger_types": trig_types,
                    "message": (
                        "This workflow has no webhook/form trigger — it runs on "
                        "a schedule or is manually triggered from the n8n editor. "
                        "The n8n Public API cannot execute such workflows on demand."
                    ),
                }

            # 3. Build the webhook URL and POST the input payload.
            path = (trigger.get("parameters", {}) or {}).get("path", "")
            if not path:
                return {
                    "ok": False,
                    "kind": "missing_webhook_path",
                    "message": "Trigger node has no `path` set — cannot invoke.",
                }
            trig_type = trigger.get("type", "")
            is_form = trig_type == "n8n-nodes-base.formTrigger"
            prefix = "form" if is_form else "webhook"
            method = (trigger.get("parameters", {}) or {}).get("httpMethod", "POST").upper()
            webhook_url = f"{base}/{prefix}/{path.lstrip('/')}"

            # 4. Invoke the webhook or form.
            req_kwargs: dict = {"timeout": 30.0, "follow_redirects": True}
            body = input_data or {}
            if method == "GET":
                resp = await c.request(method, webhook_url, params=body, **req_kwargs)
            elif is_form:
                resp = await c.request(method, webhook_url, data=body, **req_kwargs)
            else:
                resp = await c.request(method, webhook_url, json=body, **req_kwargs)

            try:
                payload = resp.json()
            except Exception:
                payload = {"raw": resp.text[:2000]}

            return {
                "ok": resp.status_code < 400,
                "kind": "webhook",
                "webhook_url": webhook_url,
                "method": method,
                "status_code": resp.status_code,
                "response": payload,
            }

    async def _activate_workflow(self, *, workflow_id: str) -> dict:
        s = get_settings()
        async with httpx.AsyncClient(base_url=s.n8n_base_url or "", timeout=20.0) as c:
            r = await c.post(
                f"/api/v1/workflows/{workflow_id}/activate",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def _deactivate_workflow(self, *, workflow_id: str) -> dict:
        s = get_settings()
        async with httpx.AsyncClient(base_url=s.n8n_base_url or "", timeout=20.0) as c:
            r = await c.post(
                f"/api/v1/workflows/{workflow_id}/deactivate",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def _ping(self) -> dict:
        """Lightweight connectivity check.

        Hits `GET /api/v1/workflows?limit=1` and returns a compact summary:
        `{"ok": True, "latency_ms": 42, "base_url": "..."}` on success or
        `{"ok": False, "error": "..."}` on any failure. Used by the
        "Test connection" button in the n8n status tab.
        """
        import time
        s = get_settings()
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(base_url=s.n8n_base_url or "", timeout=10.0) as c:
                r = await c.get(
                    "/api/v1/workflows",
                    headers=self._headers(),
                    params={"limit": 1},
                )
        except Exception as e:                                          # noqa: BLE001
            return {
                "ok": False,
                "base_url": s.n8n_base_url or "",
                "error": f"{type(e).__name__}: {e}",
            }
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "ok": r.status_code < 400,
            "status_code": r.status_code,
            "latency_ms": latency_ms,
            "base_url": s.n8n_base_url or "",
            "error": None if r.status_code < 400 else r.text[:200],
        }
