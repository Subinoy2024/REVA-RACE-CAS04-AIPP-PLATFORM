"""MCP adapter registry — single source of truth for available tools.

Each adapter is a real implementation that makes actual REST/SDK calls when
its credentials are present in `.env`. Adapters gracefully return
`ToolNotConfiguredError` when credentials are missing (no mocks).
"""

from __future__ import annotations

from typing import Dict

from backend.mcp.adapters.aws import AWSAdapter
from backend.mcp.adapters.azure import AzureAdapter
from backend.mcp.adapters.azure_devops import AzureDevOpsAdapter
from backend.mcp.adapters.base import BaseMCPAdapter
from backend.mcp.adapters.gcp import GCPAdapter
from backend.mcp.adapters.github import GitHubAdapter
from backend.mcp.adapters.github_actions import GitHubActionsAdapter
from backend.mcp.adapters.gitlab import GitLabAdapter
from backend.mcp.adapters.harness import HarnessAdapter
from backend.mcp.adapters.kubernetes import KubernetesAdapter
from backend.mcp.adapters.n8n import N8nAdapter
from backend.mcp.adapters.tekton import TektonAdapter


def build_registry() -> Dict[str, BaseMCPAdapter]:
    """Instantiate every known adapter. Adapters without credentials expose
    the tool surface but raise `ToolNotConfiguredError` on invocation.
    """
    return {
        "github": GitHubAdapter(),
        "github_actions": GitHubActionsAdapter(),
        "azure_devops": AzureDevOpsAdapter(),
        "gitlab": GitLabAdapter(),
        "harness": HarnessAdapter(),
        "tekton": TektonAdapter(),
        "kubernetes": KubernetesAdapter(),
        "azure": AzureAdapter(),
        "aws": AWSAdapter(),
        "gcp": GCPAdapter(),
        "n8n": N8nAdapter(),
    }
