"""Azure MCP adapter — azure-mgmt-resource via service principal.

Config env vars:
  AZURE_SUBSCRIPTION_ID
  AZURE_TENANT_ID
  AZURE_CLIENT_ID
  AZURE_CLIENT_SECRET
"""

from __future__ import annotations

import asyncio
import os

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class AzureAdapter(BaseMCPAdapter):
    name = "azure"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.azure_subscription_id and s.azure_tenant_id and s.azure_client_id and s.azure_client_secret)

    def _register_tools(self) -> None:
        self._register("list_resource_groups", self._list_resource_groups)
        self._register("deploy_arm", self._deploy_arm)

    def _client(self):
        from azure.identity import ClientSecretCredential
        from azure.mgmt.resource import ResourceManagementClient
        s = get_settings()
        # Push creds into env for downstream SDK use
        os.environ.setdefault("AZURE_TENANT_ID", s.azure_tenant_id or "")
        os.environ.setdefault("AZURE_CLIENT_ID", s.azure_client_id or "")
        os.environ.setdefault("AZURE_CLIENT_SECRET", s.azure_client_secret or "")
        cred = ClientSecretCredential(
            tenant_id=s.azure_tenant_id or "",
            client_id=s.azure_client_id or "",
            client_secret=s.azure_client_secret or "",
        )
        return ResourceManagementClient(cred, s.azure_subscription_id or "")

    async def _list_resource_groups(self) -> list[dict]:
        def _work():
            client = self._client()
            return [{"name": rg.name, "location": rg.location} for rg in client.resource_groups.list()]
        return await asyncio.to_thread(_work)

    async def _deploy_arm(self, *, resource_group: str, deployment_name: str, template: dict, parameters: dict | None = None) -> dict:
        def _work():
            client = self._client()
            props = {"mode": "Incremental", "template": template, "parameters": parameters or {}}
            poller = client.deployments.begin_create_or_update(
                resource_group_name=resource_group, deployment_name=deployment_name,
                parameters={"properties": props},
            )
            result = poller.result()
            return {"id": result.id, "state": result.properties.provisioning_state}
        return await asyncio.to_thread(_work)
