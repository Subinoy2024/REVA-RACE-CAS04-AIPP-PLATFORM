"""Agent-Aware MCP Guard.

Purpose:
  Turn the agent registry into a runtime security boundary. Every MCP
  tool invocation must originate from an agent that has explicitly
  declared that adapter in its skill card (`reads_mcp` or `writes_mcp`).
  A prompt-injected agent that tries to reach for an unlisted adapter is
  denied immediately.

Design (same shape as `orchestrator.progress.bind_stream_id`):
  - `_current_agent` is a `contextvars.ContextVar[str | None]`.
  - `bind_agent(name)` is a context manager that sets it for the duration
    of a `with` block (async-safe — `contextvars` cross await boundaries).
  - The LangGraph node wrapper (`orchestrator.graph._track`) binds the
    agent name around every node execution, so the "current agent" is
    always known inside agent code.
  - `MCPClient.call()` reads `current_agent()` at call time.
    - If the caller is `None` (e.g. a direct API-layer call for the
      "Commit YAML" button), the guard permits the call — public API
      routes carry their own auth story (rate limit + secret scan).
    - If the caller is a known agent, the adapter must appear in the
      agent's skill card. If not, `MCPGuardError` is raised.

Enforcement modes:
  - `GUARD_ENFORCE = "block"` (default): unlisted call → `MCPGuardError`.
  - `GUARD_ENFORCE = "warn"`:                 → log + allow.
  Controlled by env var `AIPP_MCP_GUARD` for easy demo of the boundary.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
from typing import Iterator, Optional

from backend.core.exceptions import AIPPError
from backend.core.logging import get_logger

logger = get_logger(__name__)


class MCPGuardError(AIPPError):
    """Raised when an agent tries to call an MCP adapter it did not declare."""


_current_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "aipp_current_agent", default=None,
)


@contextlib.contextmanager
def bind_agent(name: str) -> Iterator[None]:
    """Bind the given agent name as the current caller for the duration
    of the `with` block. Nested calls stack correctly."""
    token = _current_agent.set(name)
    try:
        yield
    finally:
        _current_agent.reset(token)


def current_agent() -> Optional[str]:
    return _current_agent.get()


def enforce_mode() -> str:
    return (os.environ.get("AIPP_MCP_GUARD") or "block").strip().lower()


def check(adapter: str) -> None:
    """Raise `MCPGuardError` (or log a warning) if the current agent has
    not declared `adapter` in its skill card.

    Called by `MCPClient.call()`. Public API-layer callers are exempt
    because `current_agent()` returns `None` there.
    """
    agent_name = current_agent()
    if agent_name is None:
        # No agent context = called from the API layer directly (e.g. the
        # `POST /api/deployment/commit` button). Those routes carry their
        # own guards (rate limit + secret scan + branch validation).
        return

    # Lazy import to avoid registry ↔ mcp circular import at module load.
    from backend.agents.registry import get_agent
    skill = get_agent(agent_name)
    if skill is None:
        # Unknown agent name → suspicious. Reject in block mode.
        _handle_violation(agent_name, adapter, reason="unknown_agent")
        return

    allowed = set(skill.reads_mcp) | set(skill.writes_mcp)
    if adapter in allowed:
        return

    _handle_violation(agent_name, adapter, reason="not_declared")


def _handle_violation(agent_name: str, adapter: str, *, reason: str) -> None:
    msg = (
        f"MCP guard: agent {agent_name!r} attempted to call unlisted "
        f"adapter {adapter!r} ({reason}). See docs/AGENT_REGISTRY.md § 7."
    )
    if enforce_mode() == "warn":
        logger.warning(msg)
        return
    logger.error(msg)
    raise MCPGuardError(msg)
