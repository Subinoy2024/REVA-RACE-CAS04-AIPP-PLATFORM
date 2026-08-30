"""Repository service — thin wrapper for quickly probing a repo (used by the UI's
'test connection' button, and by the orchestrator)."""

from __future__ import annotations

from backend.mcp.client import get_mcp_client
from backend.models.repository import RepositoryRequest


class RepositoryService:
    async def probe(self, req: RepositoryRequest) -> dict:
        mcp = get_mcp_client()
        meta = await mcp.call(
            "github", "get_repository",
            url=str(req.repo_url), pat=req.github_pat, branch=req.branch,
        )
        return meta
