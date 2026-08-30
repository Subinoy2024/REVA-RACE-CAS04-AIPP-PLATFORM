"""GitHub Actions MCP adapter — real REST API via bearer token.

Config env vars:
  GITHUB_ACTIONS_TOKEN   PAT with `workflow` scope (repo access)
"""

from __future__ import annotations

import httpx

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class GitHubActionsAdapter(BaseMCPAdapter):
    name = "github_actions"

    def is_configured(self) -> bool:
        return bool(get_settings().github_actions_token)

    def _register_tools(self) -> None:
        self._register("list_workflows", self._list_workflows)
        self._register("trigger_workflow", self._trigger_workflow)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {get_settings().github_actions_token or ''}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _list_workflows(self, *, owner: str, repo: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(
                f"https://api.github.com/repos/{owner}/{repo}/actions/workflows",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json().get("workflows", [])

    async def _trigger_workflow(self, *, owner: str, repo: str, workflow_id: str, ref: str = "main") -> bool:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(
                f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
                headers=self._headers(), json={"ref": ref},
            )
            return r.status_code == 204
