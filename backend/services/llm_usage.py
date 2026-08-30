"""LLM usage + cost tracking.

Because `emergentintegrations` doesn't consistently expose token counts,
we estimate them from character length (4 chars ≈ 1 token — the standard
OpenAI heuristic). The estimate is clearly labelled "estimated" in the UI
so users don't confuse it with a billing invoice.

Rates are per 1M tokens and cover the common models in the AIPP stack.
Extend `PRICE_TABLE` when the user configures a new model.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List


# Model → (prompt $/M, completion $/M). Updated Feb-2026.
# Users can override at runtime via `set_rates()`.
PRICE_TABLE: Dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o":         (2.50, 10.00),
    "gpt-4o-mini":    (0.15,  0.60),
    "gpt-4.1":        (2.00,  8.00),
    "gpt-4.1-mini":   (0.40,  1.60),
    "gpt-5":          (5.00, 20.00),
    "gpt-5-mini":     (0.50,  2.00),
    # Anthropic
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-sonnet-4-5":          (3.00, 15.00),
    "claude-opus-4-5":           (15.00, 75.00),
    # Google Gemini
    "gemini-1.5-pro":   (1.25,  5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-2.5-pro":   (1.25,  5.00),
    "gemini-2.5-flash": (0.075, 0.30),
}
_DEFAULT_RATE = (2.00, 8.00)   # fallback for unknown models


def _chars_to_tokens(chars: int) -> int:
    """OpenAI/Anthropic industry-standard heuristic: ~4 chars per token."""
    return max(0, chars // 4)


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rate_in, rate_out = PRICE_TABLE.get(model, _DEFAULT_RATE)
    return (prompt_tokens * rate_in + completion_tokens * rate_out) / 1_000_000


def estimate_cost_usd(*, provider: str, model: str,
                      prompt_tokens: int, completion_tokens: int) -> float:
    """Public wrapper around the private estimator — used by the
    agent-trace collector (iteration-27). `provider` is accepted for
    signature symmetry with future provider-specific pricing but is
    not consulted today (rate is model-keyed)."""
    _ = provider
    return _estimate_cost_usd(model, prompt_tokens, completion_tokens)


@dataclass
class LLMCall:
    agent: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


@dataclass
class LLMUsageTracker:
    calls: List[LLMCall] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, *, agent: str, provider: str, model: str,
               prompt_chars: int, completion_chars: int) -> LLMCall:
        pt = _chars_to_tokens(prompt_chars)
        ct = _chars_to_tokens(completion_chars)
        cost = _estimate_cost_usd(model, pt, ct)
        call = LLMCall(agent=agent, provider=provider, model=model,
                       prompt_tokens=pt, completion_tokens=ct, cost_usd=cost)
        with self._lock:
            self.calls.append(call)
        # Best-effort persistence to Postgres. Never let a DB blip crash
        # the calling agent — we swallow exceptions and log.
        try:
            _persist_async(call)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "llm_usage: DB persistence failed (call still recorded in memory): %s", e,
            )
        return call

    def totals(self) -> dict:
        with self._lock:
            calls = list(self.calls)
        pt = sum(c.prompt_tokens for c in calls)
        ct = sum(c.completion_tokens for c in calls)
        cost = sum(c.cost_usd for c in calls)
        # per-model breakdown
        by_model: Dict[str, dict] = {}
        for c in calls:
            b = by_model.setdefault(c.model, {"calls": 0, "prompt_tokens": 0,
                                              "completion_tokens": 0,
                                              "cost_usd": 0.0})
            b["calls"] += 1
            b["prompt_tokens"] += c.prompt_tokens
            b["completion_tokens"] += c.completion_tokens
            b["cost_usd"] += c.cost_usd
        return {
            "total_calls": len(calls),
            "total_prompt_tokens": pt,
            "total_completion_tokens": ct,
            "total_tokens": pt + ct,
            "estimated_cost_usd": round(cost, 6),
            "by_model": by_model,
            "note": "Estimated (~4 chars/token). Reset when the backend "
                    "restarts. For billing use your provider's dashboard.",
        }

    def reset(self) -> None:
        with self._lock:
            self.calls.clear()


# Process-wide singleton — reset when the backend restarts.
_TRACKER = LLMUsageTracker()


def tracker() -> LLMUsageTracker:
    return _TRACKER


# --- DB persistence (best-effort, non-blocking) ------------------------------
def _persist_async(call: "LLMCall") -> None:
    """Fire-and-forget INSERT into `llm_calls`. Safe to call from sync code.

    We keep this outside the lock so an async DB blip cannot block LLM
    tracking for other agents.
    """
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Called from a non-async context (e.g. a unit test with no loop):
        # just skip — the in-memory record is still there.
        return
    loop.create_task(_persist_call(call))


async def _persist_call(call: "LLMCall") -> None:
    from backend.database.connection import session_scope
    from backend.database.models import LLMCall as LLMCallRow
    async with session_scope() as sess:
        sess.add(LLMCallRow(
            agent=call.agent,
            provider=call.provider,
            model=call.model,
            prompt_tokens=call.prompt_tokens,
            completion_tokens=call.completion_tokens,
            cost_usd=call.cost_usd,
        ))
