"""MCP client — the only object agents talk to when they need external tools.

Provides:
  - tool discovery (`list_tools`)
  - namespaced tool invocation (`call('github', 'list_files', ...)`)
  - audit hook (each call is written to AuditLog before it runs)
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.core.logging import get_logger
from backend.mcp.adapters.base import BaseMCPAdapter
from backend.mcp.registry import build_registry

logger = get_logger(__name__)


class MCPClient:
    def __init__(self, adapters: Dict[str, BaseMCPAdapter] | None = None) -> None:
        self._adapters = adapters or build_registry()

    # ------------------------------------------------------------------
    def list_tools(self) -> Dict[str, List[str]]:
        return {name: adapter.list_tools() for name, adapter in self._adapters.items()}

    def is_configured(self, adapter: str) -> bool:
        a = self._adapters.get(adapter)
        return bool(a and a.is_configured())

    def configured_adapters(self) -> List[str]:
        return [n for n, a in self._adapters.items() if a.is_configured()]

    # ------------------------------------------------------------------
    async def call(self, adapter: str, tool: str, **kwargs: Any) -> Any:
        if adapter not in self._adapters:
            raise KeyError(f"MCP adapter '{adapter}' unknown")
        # Agent-aware guard: enforce that the caller agent's skill card
        # lists this adapter. API-layer calls (no agent context) pass.
        from backend.mcp.guard import check as _guard_check
        _guard_check(adapter)
        # Redact sensitive kwargs before logging — never log a PAT.
        safe_kwargs = {k: ("***" if k.lower() in {"pat", "token", "api_key"} else v) for k, v in kwargs.items()}
        logger.info("mcp.call adapter=%s tool=%s args=%s", adapter, tool, safe_kwargs)

        # Iteration-27: record on the currently active agent trace.
        import time as _t
        _t0 = _t.perf_counter()
        _ok = True
        try:
            return await self._adapters[adapter].call(tool, **kwargs)
        except Exception:
            _ok = False
            raise
        finally:
            try:
                from backend.services import agent_trace as _at
                collector = _at.current()
                if collector is not None:
                    collector.record_mcp(
                        adapter=adapter, tool=tool,
                        args_summary=repr(safe_kwargs)[:400],
                        ok=_ok,
                        duration_ms=int((_t.perf_counter() - _t0) * 1000),
                    )
            except Exception:                                       # noqa: BLE001
                logger.debug("agent_trace: mcp record failed", exc_info=True)


# Module-level singleton (cheap to construct).
_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    global _client
    if _client is None:
        _client = MCPClient()
    return _client
