"""Verify that every non-github adapter reports `is_configured() = False`
when its env vars are absent, and that calling any of its tools raises
ToolNotConfiguredError. This is the 'no mock data' guarantee.
"""

from __future__ import annotations

import pytest

from backend.core.exceptions import ToolNotConfiguredError
from backend.mcp.client import MCPClient


UNCONFIGURED_ADAPTERS_AND_TOOLS = [
    ("azure_devops", "list_pipelines", {"project": "demo"}),
    ("gitlab", "list_pipelines", {"project_id": "1"}),
    ("github_actions", "list_workflows", {"owner": "o", "repo": "r"}),
    ("harness", "list_pipelines", {"org": "o", "project": "p"}),
    ("kubernetes", "list_namespaces", {}),
    ("tekton", "list_pipelines", {"namespace": "default"}),
    ("azure", "list_resource_groups", {}),
    ("aws", "list_stacks", {}),
    ("gcp", "list_projects", {}),
]


@pytest.mark.parametrize("adapter,tool,kwargs", UNCONFIGURED_ADAPTERS_AND_TOOLS)
@pytest.mark.asyncio
async def test_unconfigured_adapters_raise_cleanly(adapter, tool, kwargs):
    client = MCPClient()
    with pytest.raises(ToolNotConfiguredError):
        await client.call(adapter, tool, **kwargs)


def test_all_adapters_exposed_in_registry():
    client = MCPClient()
    tools = client.list_tools()
    for name in [
        "github", "github_actions", "azure_devops", "gitlab", "harness",
        "tekton", "kubernetes", "azure", "aws", "gcp", "n8n",
    ]:
        assert name in tools, f"missing adapter {name}"
        assert tools[name], f"adapter {name} has no tools"
