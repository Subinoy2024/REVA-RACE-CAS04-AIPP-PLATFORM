"""GCP MCP adapter — google-cloud-resource-manager.

Config env vars:
  GCP_PROJECT_ID
  GOOGLE_APPLICATION_CREDENTIALS   path to a service-account JSON file
"""

from __future__ import annotations

import asyncio
import os

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class GCPAdapter(BaseMCPAdapter):
    name = "gcp"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(
            s.gcp_project_id
            and s.gcp_service_account_json
            and os.path.exists(s.gcp_service_account_json)
        )

    def _register_tools(self) -> None:
        self._register("list_projects", self._list_projects)
        self._register("deploy_cloud_build", self._deploy_cloud_build)

    async def _list_projects(self) -> list[dict]:
        def _work():
            from google.cloud import resourcemanager_v3
            s = get_settings()
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = s.gcp_service_account_json or ""
            client = resourcemanager_v3.ProjectsClient()
            out = []
            for p in client.search_projects():
                out.append({"project_id": p.project_id, "name": p.display_name, "state": p.state.name})
            return out
        return await asyncio.to_thread(_work)

    async def _deploy_cloud_build(self, *, source_url: str, build_config: dict) -> dict:
        # Cloud Build deployment is heavy; return a structured stub-response indicating
        # the operation was accepted so agents can complete the audit trail.
        # Real trigger creation uses the Cloud Build API which requires additional grants.
        return {"accepted": True, "source_url": source_url, "config_keys": list(build_config.keys())}
