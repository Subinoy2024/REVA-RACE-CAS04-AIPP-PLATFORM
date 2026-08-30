"""Base classes for MCP adapters.

An MCP adapter wraps an external system (GitHub, n8n, Azure, AWS, ...) and
exposes a small set of async `tools` — each tool is a name -> coroutine
mapping. The adapter is deliberately thin so that we can later swap the
in-process implementation for a real MCP server without changing agent code.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from backend.core.exceptions import ToolNotConfiguredError


ToolFn = Callable[..., Awaitable[Any]]


class BaseMCPAdapter:
    """Base class every MCP adapter extends."""

    name: str = "base"

    def __init__(self) -> None:
        self._tools: Dict[str, ToolFn] = {}
        self._register_tools()

    # ------------------------------------------------------------------
    # subclass hooks
    def _register_tools(self) -> None:
        """Sub-classes register their tools here via `self._register(name, fn)`."""
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Return True if the adapter has all credentials it needs."""
        return True

    # ------------------------------------------------------------------
    # public API
    def _register(self, tool_name: str, fn: ToolFn) -> None:
        self._tools[tool_name] = fn

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    async def call(self, tool: str, **kwargs: Any) -> Any:
        if not self.is_configured():
            raise ToolNotConfiguredError(
                f"MCP adapter '{self.name}' is not configured; missing credentials"
            )
        if tool not in self._tools:
            raise KeyError(f"Tool '{tool}' not exposed by adapter '{self.name}'")
        return await self._tools[tool](**kwargs)
