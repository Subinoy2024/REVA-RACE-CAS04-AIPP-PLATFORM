"""Harness MCP adapter — REST API with x-api-key header.

Config env vars:
  HARNESS_BASE_URL     defaults to https://app.harness.io
  HARNESS_ACCOUNT_ID   account identifier
  HARNESS_API_KEY      API key with pipeline read/execute scope
"""

from __future__ import annotations

import httpx

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class HarnessAdapter(BaseMCPAdapter):
    name = "harness"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.harness_api_key and s.harness_account_id)

    def _register_tools(self) -> None:
        self._register("list_pipelines", self._list_pipelines)
        self._register("trigger_pipeline", self._trigger_pipeline)

    def _headers(self) -> dict:
        return {"x-api-key": get_settings().harness_api_key or "", "Accept": "application/json"}

    def _params(self, extra: dict | None = None) -> dict:
        s = get_settings()
        base = {"accountIdentifier": s.harness_account_id}
        if extra:
            base.update(extra)
        return base

    async def _list_pipelines(self, *, org: str, project: str) -> list[dict]:
        s = get_settings()
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(
                f"{s.harness_base_url.rstrip('/')}/pipeline/api/pipelines/list",
                headers=self._headers(),
                params=self._params({"orgIdentifier": org, "projectIdentifier": project}),
            )
            r.raise_for_status()
            data = r.json().get("data") or {}
            return data.get("content", [])

    async def _trigger_pipeline(self, *, org: str, project: str, pipeline_id: str) -> dict:
        s = get_settings()
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(
                f"{s.harness_base_url.rstrip('/')}/pipeline/api/pipeline/execute/{pipeline_id}",
                headers=self._headers(),
                params=self._params({"orgIdentifier": org, "projectIdentifier": project}),
            )
            r.raise_for_status()
            return r.json()
