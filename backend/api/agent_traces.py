"""Agent execution trace API — iteration-27.

Exposes the `agent_traces` rows written by the LangGraph node wrappers so
the frontend can render a timeline + per-agent card for any past run.

Endpoint list
-------------
GET /api/agents/traces?run_id=<uuid>
    Ordered list of traces for a single run. Public in dev — auth-guard
    it via `Depends(get_current_user)` before shipping to production.

GET /api/agents/traces/latest
    Last 20 completed pipeline runs with an aggregated trace summary
    (total duration, total cost, number of agents that failed). Feeds
    the "Recent runs" dropdown in the Agent Trace tab.

GET /api/agents/skills
    Static skill-card registry — what each agent is *allowed* to do.
    Renders alongside the actual usage so a reviewer can spot delta
    ("declared 3 skills, used 2").
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, select

from backend.database.connection import get_session
from backend.database.models import AgentTrace, PipelineRun

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# Skills registry (static)
# ---------------------------------------------------------------------------
@router.get("/skills")
async def list_skills() -> dict:
    """Return each agent's declared skill card so the UI can render
    'skills declared vs skills used' comparisons for observability."""
    try:
        from backend.agents.registry import list_agents, registry_size
        if registry_size() == 0:
            # Lazy-populate (module-level `_populate()` may not have fired
            # if this endpoint is the first import into agents.registry).
            from backend.agents.registry import _populate
            _populate()
        cards = [a.to_card() for a in list_agents()]
    except Exception:                                     # noqa: BLE001
        cards = []
    return {"agents": cards}


# ---------------------------------------------------------------------------
# Per-run traces
# ---------------------------------------------------------------------------
@router.get("/traces")
async def get_traces(run_id: str = Query(..., min_length=8)) -> dict:
    """Return the ordered trace rows for a single pipeline run."""
    from backend.database.connection import session_scope
    import uuid as _uuid
    try:
        rid = _uuid.UUID(run_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"run_id is not a valid UUID: {run_id!r}")

    async with session_scope() as sess:
        result = await sess.execute(
            select(AgentTrace)
            .where(AgentTrace.run_id == rid)
            .order_by(AgentTrace.step_index)
        )
        rows = result.scalars().all()

        pr = (await sess.execute(
            select(PipelineRun).where(PipelineRun.id == rid)
        )).scalar_one_or_none()

    def _row(r: AgentTrace) -> dict:
        return {
            "id": str(r.id),
            "agent_name": r.agent_name,
            "step_index": r.step_index,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "duration_ms": r.duration_ms,
            "input_summary": r.input_summary or {},
            "output_summary": r.output_summary or {},
            "llm_provider": r.llm_provider,
            "llm_model": r.llm_model,
            "prompt_text": r.prompt_text,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_usd": float(r.cost_usd or 0.0),
            "skills_declared": r.skills_declared or [],
            "mcp_calls": r.mcp_calls or [],
            "status": r.status,
            "error": r.error,
        }

    return {
        "run_id": run_id,
        "run_meta": {
            "repository_url": pr.repository_url if pr else None,
            "ci_platform": pr.ci_platform if pr else None,
            "cloud_platform": pr.cloud_platform if pr else None,
            "custom_requirement": pr.custom_requirement if pr else None,
            "generation_seconds": float(pr.generation_seconds) if pr else None,
            "status": pr.status if pr else None,
        } if pr else None,
        "traces": [_row(r) for r in rows],
        "totals": {
            "duration_ms": sum(r.duration_ms for r in rows),
            "prompt_tokens": sum(r.prompt_tokens for r in rows),
            "completion_tokens": sum(r.completion_tokens for r in rows),
            "cost_usd": sum(float(r.cost_usd or 0.0) for r in rows),
            "mcp_call_count": sum(len(r.mcp_calls or []) for r in rows),
            "agent_count": len(rows),
            "failed_count": sum(1 for r in rows if r.status == "error"),
        },
    }


# ---------------------------------------------------------------------------
# Recent runs (dropdown feed)
# ---------------------------------------------------------------------------
@router.get("/traces/latest")
async def latest_runs(limit: int = Query(20, ge=1, le=200)) -> dict:
    """Return the N most recent pipeline runs with their aggregate trace
    summary — powers the 'Recent runs' selector in the Agent Trace tab."""
    from backend.database.connection import session_scope

    async with session_scope() as sess:
        runs = (await sess.execute(
            select(PipelineRun).order_by(desc(PipelineRun.created_at)).limit(limit)
        )).scalars().all()

        # Fetch traces per run (small N, so N+1 is fine for the thesis scope).
        out: list[dict[str, Any]] = []
        for pr in runs:
            traces = (await sess.execute(
                select(AgentTrace).where(AgentTrace.run_id == pr.id)
            )).scalars().all()
            out.append({
                "run_id": str(pr.id),
                "repository_url": pr.repository_url,
                "ci_platform": pr.ci_platform,
                "cloud_platform": pr.cloud_platform,
                "created_at": pr.created_at.isoformat() if pr.created_at else None,
                "status": pr.status,
                "trace_count": len(traces),
                "total_duration_ms": sum(t.duration_ms for t in traces),
                "total_cost_usd": sum(float(t.cost_usd or 0.0) for t in traces),
                "failed_agents": sum(1 for t in traces if t.status == "error"),
            })
    return {"runs": out}
