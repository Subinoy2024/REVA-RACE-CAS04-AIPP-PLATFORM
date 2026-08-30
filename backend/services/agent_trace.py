"""Agent execution trace collector.

Iteration-27 · Observability story for the thesis Evaluation chapter.

Design
------
Each LangGraph node is wrapped in `graph._track()` — that wrapper now
also opens a **TraceCollector** on entry and closes it on exit. While the
collector is open, the current-agent contextvar points to it, so:

  * `agents/base.BaseAgent._chat_json()` can record the prompt / tokens
    / cost it sent to the LLM;
  * `mcp/client.MCPClient.call()` can append the (adapter, tool,
    args_summary, ok, duration_ms) of every tool invocation;
  * `mcp/guard.check()` can record the agent's declared skill list.

On close, the collector snapshots the *keys* of what the agent added to
the LangGraph state (never the full payload — that lives in the
pipeline_runs row already) and INSERTs one `agent_traces` row.

Contextvars — not thread-locals — because LangGraph nodes are async
coroutines. Any concurrent generation runs get their own collector.
"""

from __future__ import annotations

import contextvars
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional

from backend.core.logging import get_logger
from backend.database.connection import session_scope
from backend.database.models import AgentTrace

logger = get_logger(__name__)


# Truncate long prompt strings so a single row never blows past a few KB.
_PROMPT_TRUNC = 8_000


@dataclass
class _McpCall:
    adapter: str
    tool: str
    args_summary: str
    ok: bool
    duration_ms: int


@dataclass
class TraceCollector:
    """Live, in-flight trace for a single agent invocation."""
    run_id: uuid.UUID
    agent_name: str
    step_index: int
    started_at: float = field(default_factory=time.time)

    # LLM aggregates (agents may call the LLM 1–3 times on validation retries).
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    prompt_text_parts: List[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    # MCP call log.
    mcp_calls: List[_McpCall] = field(default_factory=list)
    skills_declared: List[str] = field(default_factory=list)

    # Populated from the returned state delta in `finalize()`.
    input_keys: List[str] = field(default_factory=list)
    output_keys: List[str] = field(default_factory=list)

    status: str = "ok"
    error: Optional[str] = None

    # -----------------------------------------------------------------
    # Recording API — called by BaseAgent / MCPClient / MCPGuard.
    # -----------------------------------------------------------------
    def record_llm(
        self, *,
        provider: str, model: str, prompt: str,
        prompt_tokens: int = 0, completion_tokens: int = 0, cost_usd: float = 0.0,
    ) -> None:
        self.llm_provider = provider
        self.llm_model = model
        # Concatenate all prompts an agent sent this run (retries included).
        self.prompt_text_parts.append(prompt)
        self.prompt_tokens += int(prompt_tokens or 0)
        self.completion_tokens += int(completion_tokens or 0)
        self.cost_usd += float(cost_usd or 0.0)

    def record_mcp(self, *, adapter: str, tool: str,
                   args_summary: str, ok: bool, duration_ms: int) -> None:
        self.mcp_calls.append(_McpCall(
            adapter=adapter, tool=tool,
            args_summary=(args_summary or "")[:400],
            ok=ok, duration_ms=int(duration_ms or 0),
        ))

    def declare_skills(self, skills: List[str]) -> None:
        # Idempotent — the same guard.check() may fire many times per agent.
        self.skills_declared = list({*self.skills_declared, *skills})

    def mark_error(self, err: BaseException) -> None:
        self.status = "error"
        self.error = str(err)[:2000]

    # -----------------------------------------------------------------
    # Finalisation — writes one row into `agent_traces`.
    # -----------------------------------------------------------------
    async def finalize(self, *, input_snapshot: dict, output_snapshot: dict) -> None:
        ended = time.time()
        duration_ms = int((ended - self.started_at) * 1000)
        prompt_text = ("\n\n---\n\n".join(self.prompt_text_parts))[:_PROMPT_TRUNC]

        row = AgentTrace(
            run_id=self.run_id,
            agent_name=self.agent_name,
            step_index=self.step_index,
            duration_ms=duration_ms,
            input_summary={
                "keys_present": sorted(input_snapshot.keys()) if isinstance(input_snapshot, dict) else [],
                "custom_requirement": (input_snapshot or {}).get("custom_requirement", "")[:400],
                "ci_platform": (input_snapshot or {}).get("ci_platform"),
                "cloud_platform": (input_snapshot or {}).get("cloud_platform"),
                "pipeline_type": (input_snapshot or {}).get("pipeline_type"),
            },
            output_summary={
                "keys_added": sorted(output_snapshot.keys()) if isinstance(output_snapshot, dict) else [],
                "sizes": {
                    k: (len(v) if isinstance(v, (str, list, dict)) else None)
                    for k, v in (output_snapshot or {}).items()
                },
            },
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            prompt_text=prompt_text or None,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            cost_usd=self.cost_usd,
            skills_declared=sorted(self.skills_declared),
            mcp_calls=[
                {
                    "adapter": c.adapter, "tool": c.tool,
                    "args_summary": c.args_summary,
                    "ok": c.ok, "duration_ms": c.duration_ms,
                }
                for c in self.mcp_calls
            ],
            status=self.status,
            error=self.error,
        )
        try:
            async with session_scope() as sess:
                sess.add(row)
        except Exception as e:                                    # noqa: BLE001
            # Never break generation for observability — just warn.
            logger.warning(
                "agent_trace: failed to persist trace for agent=%s run=%s: %s",
                self.agent_name, self.run_id, e,
            )


# ---------------------------------------------------------------------------
# Contextvar plumbing
# ---------------------------------------------------------------------------
_CURRENT: contextvars.ContextVar[Optional[TraceCollector]] = contextvars.ContextVar(
    "aipp_current_agent_trace", default=None,
)


def current() -> Optional[TraceCollector]:
    """Return the trace collector for the *currently executing* agent
    node, or ``None`` outside of a LangGraph run (e.g. direct API tests)."""
    return _CURRENT.get()


class bind:
    """Context manager that installs a `TraceCollector` and yields it."""
    def __init__(self, collector: TraceCollector) -> None:
        self._c = collector
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> TraceCollector:
        self._token = _CURRENT.set(self._c)
        return self._c

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _CURRENT.reset(self._token)
