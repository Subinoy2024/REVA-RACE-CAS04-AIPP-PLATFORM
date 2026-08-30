"""LLM usage / cost endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import get_session
from backend.database.models import LLMCall as LLMCallRow
from backend.services.llm_usage import tracker

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/usage")
async def get_llm_usage() -> dict:
    """Return the current LLM usage estimate (tokens + $ per model).

    In-memory counters — reset when the backend restarts. For historical
    figures across restarts, use `/usage/history`.
    """
    return tracker().totals()


@router.post("/usage/reset")
async def reset_llm_usage() -> dict:
    """Zero out the counters — useful before a benchmark batch."""
    tracker().reset()
    return {"ok": True, "message": "LLM usage counters reset"}


@router.get("/usage/history")
async def get_llm_usage_history(
    limit: int = 200,
    sess: AsyncSession = Depends(get_session),
) -> dict:
    """Historical LLM calls persisted to Postgres.

    Populated in real time by `services.llm_usage.record()`. Unlike the
    in-memory tracker (`GET /usage`), this survives container restarts —
    exactly what the thesis Evaluation chapter needs for a stable
    per-agent cost trace over a batch run.

    Response:
        {
          "total_calls":    <int>,
          "total_tokens":   <int>,
          "total_cost_usd": <float>,
          "by_agent":  {agent → {calls, prompt_tok, completion_tok, cost}},
          "by_model":  {model → same shape},
          "recent":    [<LLMCall dict>, ...]  (most recent `limit` rows)
        }
    """
    # ---- aggregates: total ----
    total_q = await sess.execute(select(
        func.count(LLMCallRow.id),
        func.coalesce(func.sum(LLMCallRow.prompt_tokens), 0),
        func.coalesce(func.sum(LLMCallRow.completion_tokens), 0),
        func.coalesce(func.sum(LLMCallRow.cost_usd), 0.0),
    ))
    n, pt, ct, cost = total_q.one()

    # ---- aggregates: by agent ----
    agent_q = await sess.execute(select(
        LLMCallRow.agent,
        func.count(LLMCallRow.id),
        func.coalesce(func.sum(LLMCallRow.prompt_tokens), 0),
        func.coalesce(func.sum(LLMCallRow.completion_tokens), 0),
        func.coalesce(func.sum(LLMCallRow.cost_usd), 0.0),
    ).group_by(LLMCallRow.agent))
    by_agent = {
        row[0]: {"calls": row[1], "prompt_tokens": row[2],
                 "completion_tokens": row[3], "cost_usd": float(row[4])}
        for row in agent_q.all()
    }

    # ---- aggregates: by model ----
    model_q = await sess.execute(select(
        LLMCallRow.model,
        func.count(LLMCallRow.id),
        func.coalesce(func.sum(LLMCallRow.prompt_tokens), 0),
        func.coalesce(func.sum(LLMCallRow.completion_tokens), 0),
        func.coalesce(func.sum(LLMCallRow.cost_usd), 0.0),
    ).group_by(LLMCallRow.model))
    by_model = {
        row[0]: {"calls": row[1], "prompt_tokens": row[2],
                 "completion_tokens": row[3], "cost_usd": float(row[4])}
        for row in model_q.all()
    }

    # ---- most recent N ----
    recent_q = await sess.execute(
        select(LLMCallRow).order_by(LLMCallRow.created_at.desc()).limit(max(1, min(limit, 1000)))
    )
    recent = [
        {
            "id": str(r.id),
            "agent": r.agent,
            "provider": r.provider,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_usd": float(r.cost_usd),
            "created_at": r.created_at.isoformat(),
        }
        for r in recent_q.scalars().all()
    ]

    return {
        "total_calls": n,
        "total_tokens": int(pt) + int(ct),
        "total_prompt_tokens": int(pt),
        "total_completion_tokens": int(ct),
        "total_cost_usd": round(float(cost), 6),
        "by_agent": by_agent,
        "by_model": by_model,
        "recent": recent,
        "note": (
            "Persisted to Postgres. Survives container restarts. Cost is "
            "estimated (~4 chars/token) at insert time and stored as a "
            "scalar for fast aggregation."
        ),
    }
