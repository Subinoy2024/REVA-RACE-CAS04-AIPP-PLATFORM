"""GitLab MCP adapter — REST API v4 with PRIVATE-TOKEN header.

Config env vars:
  GITLAB_URL     defaults to https://gitlab.com
  GITLAB_TOKEN   personal or project access token with api scope
"""

from __future__ import annotations

import httpx

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class GitLabAdapter(BaseMCPAdapter):
    name = "gitlab"

    def is_configured(self) -> bool:
        return bool(get_settings().gitlab_token)

    def _register_tools(self) -> None:
        self._register("list_pipelines", self._list_pipelines)
        self._register("trigger_pipeline", self._trigger_pipeline)

    def _headers(self) -> dict:
        return {"PRIVATE-TOKEN": get_settings().gitlab_token or "", "Accept": "application/json"}

    def _base(self) -> str:
        return get_settings().gitlab_url.rstrip("/") + "/api/v4"

    async def _list_pipelines(self, *, project_id: str | int, per_page: int = 20) -> list[dict]:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(
                f"{self._base()}/projects/{project_id}/pipelines",
                headers=self._headers(), params={"per_page": per_page},
            )
            r.raise_for_status()
            return r.json()

    async def _trigger_pipeline(self, *, project_id: str | int, ref: str = "main") -> dict:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(
                f"{self._base()}/projects/{project_id}/pipeline",
                headers=self._headers(), params={"ref": ref},
            )
            r.raise_for_status()
            return r.json()
