"""Azure DevOps MCP adapter — REST API via PAT (Basic auth: ':<pat>' base64).

Config env vars:
  AZURE_DEVOPS_ORG_URL   e.g. https://dev.azure.com/my-org
  AZURE_DEVOPS_PAT       personal access token with Pipelines: Read
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class AzureDevOpsAdapter(BaseMCPAdapter):
    name = "azure_devops"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.azure_devops_org_url and s.azure_devops_pat)

    def _register_tools(self) -> None:
        self._register("list_pipelines", self._list_pipelines)
        self._register("trigger_pipeline", self._trigger_pipeline)

    def _headers(self) -> dict:
        pat = get_settings().azure_devops_pat or ""
        token = base64.b64encode(f":{pat}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Accept": "application/json"}

    def _base(self) -> str:
        return (get_settings().azure_devops_org_url or "").rstrip("/")

    async def _list_pipelines(self, *, project: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(f"{self._base()}/{project}/_apis/pipelines?api-version=7.1",
                            headers=self._headers())
            r.raise_for_status()
            return r.json().get("value", [])

    async def _trigger_pipeline(self, *, project: str, pipeline_id: int, branch: str = "refs/heads/main") -> dict:
        payload: dict[str, Any] = {"resources": {"repositories": {"self": {"refName": branch}}}}
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(
                f"{self._base()}/{project}/_apis/pipelines/{pipeline_id}/runs?api-version=7.1",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            return r.json()
