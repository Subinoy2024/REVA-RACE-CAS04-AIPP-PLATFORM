"""In-process progress bus used to stream agent status to SSE clients.

Design:
    - Every pipeline run is assigned a `stream_id`.
    - The LangGraph nodes call `publish(stream_id, event)` on entry/exit.
    - The SSE endpoint calls `subscribe(stream_id)` to obtain an async
      iterator of events.
    - When the graph finishes, the orchestrator publishes a final
      `stream_done` event which closes the subscriber loop.
    - A `contextvars.ContextVar` (`_CURRENT_STREAM_ID`) also exposes the
      active stream_id to any code path (e.g. the LLM chat wrapper) that
      wants to emit token-level deltas without threading `stream_id`
      through every function signature.

Kept intentionally in-process — a single Gradio user talks to a single
FastAPI worker, so we don't need Redis pub/sub here. If we ever add
multi-worker gunicorn, swap `_BUSES` for a Redis-backed queue.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import time
import uuid
from typing import AsyncIterator, Dict, Literal, Optional, TypedDict


EventStatus = Literal["running", "done", "failed"]


class ProgressEvent(TypedDict, total=False):
    """One progress signal emitted by an agent node."""
    stream_id: str
    seq: int
    agent: str                 # e.g. "repository_analysis"
    status: EventStatus
    detail: str                # short human-readable status
    ts: float                  # unix timestamp
    total_agents: int          # for progress bar rendering
    agent_index: int           # 0-based index of the current agent
    kind: Literal["agent", "result", "error", "done"]
    payload: dict              # for kind="result" — final generation output


# ---------------------------------------------------------------------------
# Registry — one bus per active stream_id
# ---------------------------------------------------------------------------
class _Bus:
    """Wraps an asyncio.Queue plus completion sentinel handling."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self.seq: int = 0
        self.closed: bool = False

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq


_BUSES: Dict[str, _Bus] = {}
_LOCK = asyncio.Lock()


async def create_stream() -> str:
    """Register a new stream_id and return it."""
    async with _LOCK:
        sid = uuid.uuid4().hex
        _BUSES[sid] = _Bus()
        return sid


async def publish(
    stream_id: Optional[str],
    *,
    agent: str,
    status: EventStatus,
    detail: str = "",
    kind: str = "agent",
    payload: Optional[dict] = None,
    total_agents: Optional[int] = None,
    agent_index: Optional[int] = None,
) -> None:
    """Emit one event to subscribers of `stream_id`.

    Silently no-ops if the stream_id is falsy or already closed — this lets
    the graph run happily even when nobody is listening (e.g. unit tests).
    """
    if not stream_id or stream_id not in _BUSES:
        return
    bus = _BUSES[stream_id]
    if bus.closed:
        return
    event: ProgressEvent = {
        "stream_id": stream_id,
        "seq": bus.next_seq(),
        "agent": agent,
        "status": status,
        "detail": detail,
        "ts": time.time(),
        "kind": kind,       # type: ignore[typeddict-item]
        "payload": payload or {},
    }
    if total_agents is not None:
        event["total_agents"] = total_agents
    if agent_index is not None:
        event["agent_index"] = agent_index
    await bus.queue.put(event)


async def close(stream_id: Optional[str]) -> None:
    """Mark the stream as done and unblock any waiting subscriber."""
    if not stream_id or stream_id not in _BUSES:
        return
    bus = _BUSES[stream_id]
    if bus.closed:
        return
    bus.closed = True
    await bus.queue.put({
        "stream_id": stream_id, "seq": bus.next_seq(),
        "agent": "orchestrator", "status": "done", "detail": "stream closed",
        "ts": time.time(), "kind": "done", "payload": {},
    })


async def subscribe(stream_id: str) -> AsyncIterator[ProgressEvent]:
    """Yield events for the given stream_id until it is closed.

    The caller is responsible for calling `discard(stream_id)` when done,
    otherwise the bus lingers in memory.
    """
    if stream_id not in _BUSES:
        return
    bus = _BUSES[stream_id]
    while True:
        event = await bus.queue.get()
        yield event
        if event.get("kind") == "done":
            break


async def discard(stream_id: Optional[str]) -> None:
    """Delete a stream_id from the registry (call after SSE ends)."""
    if not stream_id:
        return
    async with _LOCK:
        _BUSES.pop(stream_id, None)


def active_stream_count() -> int:
    """Test helper — how many streams are currently registered."""
    return len(_BUSES)


# ---------------------------------------------------------------------------
# Context-local `stream_id` — lets deep code paths emit events without
# receiving `stream_id` through every function signature.
# ---------------------------------------------------------------------------
_CURRENT_STREAM_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "aipp_stream_id", default=None,
)


def current_stream_id() -> Optional[str]:
    """Return the stream_id bound to the current async context, or None."""
    return _CURRENT_STREAM_ID.get()


@contextlib.contextmanager
def bind_stream_id(stream_id: Optional[str]):
    """Bind `stream_id` for the duration of a `with` block.

    Used by `graph._track()` to make the run's stream_id visible to any
    LLM call issued by the wrapped agent — see `agents/base.py` where the
    token-level streaming path reads it.
    """
    token = _CURRENT_STREAM_ID.set(stream_id)
    try:
        yield
    finally:
        _CURRENT_STREAM_ID.reset(token)
