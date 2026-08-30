"""Pipeline-generation endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import AIPPError, LLMError
from backend.core.logging import get_logger
from backend.core.rate_limit import enforce_generate_limit
from backend.database.connection import get_session
from backend.database.models import PipelineRun
from backend.models.pipeline import CIPlatform, CLOUD_TARGETS, CloudPlatform, DeploymentTarget
from backend.models.repository import RepositoryRequest
from backend.orchestrator import progress
from backend.orchestrator.graph import AGENT_ORDER, TOTAL_AGENTS
from backend.services.pipeline_service import PipelineService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


class GenerateRequest(BaseModel):
    repo_url: HttpUrl
    github_pat: str = Field(..., min_length=8)
    branch: str = "main"
    ci_platform: CIPlatform
    cloud_platform: CloudPlatform
    custom_requirement: Optional[str] = ""
    # New in iteration 14: honour the UI Pipeline-Scope selector at the
    # generator level (was previously only used to prime the LLM planner).
    pipeline_type: str = "all_in_one"
    agent_pool: Optional[str] = None   # None → Microsoft-hosted ubuntu-22.04
    # Iteration-20 (Terraform-default-everywhere + Bicep opt-in):
    # AIPP defaults to Terraform for infra across ALL clouds. Users can
    # opt-in to Bicep by sending `iac_tool="bicep"`. The escape hatch is
    # honoured ONLY for Azure — on AWS/GCP it is ignored (Bicep is
    # Azure-specific and would fail to run).
    iac_tool: Literal["terraform", "bicep"] = "terraform"
    # Iteration-21: explicit deployment target inside the chosen cloud.
    # `unspecified` (default) means the planner agent decides based on repo
    # analysis. Any other value is validated against the cloud in _validate().
    deployment_target: DeploymentTarget = DeploymentTarget.unspecified

    def _validate(self) -> None:
        """Reject nonsensical cloud/target combinations."""
        if self.deployment_target == DeploymentTarget.unspecified:
            return
        valid = CLOUD_TARGETS.get(self.cloud_platform.value, [])
        if self.deployment_target.value not in valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"deployment_target='{self.deployment_target.value}' is not valid "
                    f"for cloud='{self.cloud_platform.value}'. "
                    f"Allowed: {valid}"
                ),
            )


@router.get("/deployment-targets")
async def list_deployment_targets() -> dict:
    """Return valid deployment targets grouped by cloud — feeds the UI dropdown."""
    from backend.models.pipeline import TARGET_LABELS
    return {
        "clouds": {
            cloud: [
                {"value": t, "label": TARGET_LABELS.get(t, t)}
                for t in ["unspecified"] + targets
            ]
            for cloud, targets in CLOUD_TARGETS.items()
        }
    }


@router.post("/generate")
async def generate_pipeline(body: GenerateRequest, request: Request) -> dict:
    enforce_generate_limit(request)
    body._validate()
    req = RepositoryRequest(repo_url=body.repo_url, github_pat=body.github_pat, branch=body.branch)
    try:
        return await PipelineService().generate(
            req=req,
            ci_platform=body.ci_platform,
            cloud_platform=body.cloud_platform,
            custom_requirement=body.custom_requirement or "",
            pipeline_type=body.pipeline_type,
            agent_pool=body.agent_pool,
            iac_tool=body.iac_tool,
            deployment_target=body.deployment_target.value,
        )
    except LLMError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LLM error: {e}")
    except AIPPError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/generate/agents")
async def list_generate_agents() -> dict:
    """Return the ordered agent list so the UI can render 7 progress rows."""
    return {
        "total": TOTAL_AGENTS,
        "agents": [
            {"index": i, "name": name, "label": label}
            for i, (name, label) in enumerate(AGENT_ORDER)
        ],
    }


@router.post("/generate/stream")
async def generate_pipeline_stream(body: GenerateRequest, request: Request) -> StreamingResponse:
    """Server-Sent Events variant of `POST /generate`.

    Emits `data:` frames of shape:
      {"kind": "agent", "agent": "...", "status": "running|done|failed",
       "agent_index": i, "total_agents": 7, "detail": "...", "seq": n}
    then a final:
      {"kind": "result", "payload": {...same shape as /generate...}}
    then:
      {"kind": "done"}
    """
    enforce_generate_limit(request)
    body._validate()
    req = RepositoryRequest(repo_url=body.repo_url, github_pat=body.github_pat, branch=body.branch)

    stream_id = await progress.create_stream()

    async def _run_and_finalise() -> None:
        try:
            result = await PipelineService().generate(
                req=req,
                ci_platform=body.ci_platform,
                cloud_platform=body.cloud_platform,
                custom_requirement=body.custom_requirement or "",
                stream_id=stream_id,
                pipeline_type=body.pipeline_type,
                agent_pool=body.agent_pool,
                iac_tool=body.iac_tool,
                deployment_target=body.deployment_target.value,
            )
            await progress.publish(
                stream_id, agent="orchestrator", status="done",
                detail="pipeline generated",
                kind="result", payload=result,
            )
        except LLMError as e:
            await progress.publish(
                stream_id, agent="orchestrator", status="failed",
                detail=f"LLM error: {e}", kind="error",
                payload={"detail": str(e), "type": "llm_error"},
            )
        except AIPPError as e:
            await progress.publish(
                stream_id, agent="orchestrator", status="failed",
                detail=str(e), kind="error",
                payload={"detail": str(e), "type": "aipp_error"},
            )
        except Exception as e:                                # noqa: BLE001
            logger.exception("stream run failed")
            await progress.publish(
                stream_id, agent="orchestrator", status="failed",
                detail=str(e), kind="error",
                payload={"detail": str(e), "type": "unexpected"},
            )
        finally:
            await progress.close(stream_id)

    task = asyncio.create_task(_run_and_finalise())

    async def _sse():
        try:
            async for event in progress.subscribe(stream_id):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            # Ensure the background task is awaited so exceptions surface.
            if not task.done():
                task.cancel()
            await progress.discard(stream_id)

    return StreamingResponse(_sse(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # nginx: don't buffer SSE
    })


@router.get("/runs")
async def list_runs(limit: int = 20, sess: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await sess.execute(select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(limit))).scalars().all()
    return [
        {
            "id": str(r.id),
            "repository_url": r.repository_url,
            "branch": r.branch,
            "ci_platform": r.ci_platform,
            "cloud_platform": r.cloud_platform,
            "generation_seconds": r.generation_seconds,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# ===========================================================================
# RAG endpoint — `pgvector` similarity search over past pipeline runs
# ===========================================================================
@router.get("/similar")
async def similar_pipelines(
    q: str,
    limit: int = 5,
    sess: AsyncSession = Depends(get_session),
) -> dict:
    """Return the `limit` most similar past pipeline runs to query text `q`.

    Uses cosine distance against the `pipeline_embeddings` table populated
    by `pipeline_service.generate()`. The query text is embedded on the
    fly by `EmbeddingService`; results include the run id, repo, target,
    and cosine similarity score (1.0 = identical, 0.0 = orthogonal).

    Falls back gracefully when:
      * pgvector extension missing → HTTP 501 with clear message
      * no embeddings yet → returns empty list, `hits: 0`
    """
    from sqlalchemy import text as sa_text
    from backend.services.embedding_service import EmbeddingService

    if not q or not q.strip():
        raise HTTPException(400, "q parameter is required")
    if limit < 1 or limit > 50:
        raise HTTPException(400, "limit must be 1..50")

    svc = EmbeddingService()
    qvec = await svc.embed(q.strip())
    vec_literal = "[" + ",".join(f"{v:.6f}" for v in qvec) + "]"

    try:
        # cosine distance operator `<=>` — smallest = closest.
        # Similarity = 1 - distance.
        result = await sess.execute(
            sa_text("""
                SELECT
                  pe.run_id::text     AS run_id,
                  pr.repository_url   AS repo,
                  pr.ci_platform      AS ci,
                  pr.cloud_platform   AS cloud,
                  pr.status           AS status,
                  pr.created_at       AS created_at,
                  (1 - (pe.embedding <=> CAST(:qvec AS vector))) AS similarity
                FROM pipeline_embeddings pe
                JOIN pipeline_runs pr ON pr.id = pe.run_id
                ORDER BY pe.embedding <=> CAST(:qvec AS vector)
                LIMIT :lim
            """),
            {"qvec": vec_literal, "lim": limit},
        )
        rows = result.mappings().all()
    except Exception as e:                                       # noqa: BLE001
        msg = str(e).lower()
        if "extension" in msg or 'type "vector"' in msg or "hnsw" in msg:
            raise HTTPException(
                501,
                "pgvector extension not available — run migration 34_pgvector_rag",
            )
        # Table might not exist yet (fresh DB, no runs embedded)
        if "pipeline_embeddings" in msg and "does not exist" in msg:
            return {"query": q, "hits": 0, "results": []}
        raise HTTPException(500, f"similarity query failed: {e}")

    return {
        "query": q,
        "hits": len(rows),
        "results": [
            {
                "run_id": r["run_id"],
                "repo": r["repo"],
                "ci": r["ci"],
                "cloud": r["cloud"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "similarity": round(float(r["similarity"]), 4),
            }
            for r in rows
        ],
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str, sess: AsyncSession = Depends(get_session)) -> dict:
    row = (await sess.execute(select(PipelineRun).where(PipelineRun.id == run_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "id": str(row.id),
        "repository_url": row.repository_url,
        "branch": row.branch,
        "ci_platform": row.ci_platform,
        "cloud_platform": row.cloud_platform,
        "custom_requirement": row.custom_requirement,
        "analysis": row.analysis_json,
        "plan": row.plan_json,
        "environments": row.environments_json,
        "validation": row.validation_json,
        "yaml": row.yaml_output,
        "explanation": row.explanation,
        "generation_seconds": row.generation_seconds,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }


# ===========================================================================
# HITL — approve / reject endpoints (called by Slack card in n8n workflow #16)
# ===========================================================================
def _require_proxy_key(authorization: Optional[str]) -> None:
    """Same auth as /api/proxy/* — callable from n8n Slack card via the
    single shared API key. Never accept unauthenticated HITL clicks."""
    import hmac
    from backend.core.config import get_settings
    settings = get_settings()
    if not settings.proxy_api_key:
        raise HTTPException(503, "proxy_api_key not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    presented = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(presented, settings.proxy_api_key):
        raise HTTPException(401, "invalid api key")


async def _record_hitl_decision(sess: AsyncSession, run_id: str, decision: str) -> dict:
    row = (await sess.execute(
        select(PipelineRun).where(PipelineRun.id == run_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "run not found")
    # Persist as a status transition + analysis annotation.
    row.status = f"hitl_{decision}"
    row.analysis_json = {
        **(row.analysis_json or {}),
        "hitl": {"decision": decision, "decided_at": _now_iso()},
    }
    await sess.commit()
    return {"run_id": run_id, "decision": decision, "status": row.status}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


@router.post("/{run_id}/approve", status_code=200)
async def approve_run(
    run_id: str,
    authorization: Optional[str] = Header(None),
    sess: AsyncSession = Depends(get_session),
) -> dict:
    """HITL approve — records the decision and fires downstream n8n flows.

    On approval we chain into #02 IaC Drift + #11 SOP so the operator's
    single click ripples through the whole automation graph.
    """
    _require_proxy_key(authorization)
    result = await _record_hitl_decision(sess, run_id, "approved")

    # Best-effort downstream fan-out — never fails the approve call.
    from backend.services.n8n_hooks import fire
    await fire("sop", {"body": {"incident_id": run_id,
                                "rca_summary": "pipeline approved for deployment"}})
    await fire("iac_drift", {"body": {"trigger": "post_approve",
                                      "run_id": run_id}})
    return {**result, "downstream": ["sop", "iac_drift"]}


@router.post("/{run_id}/reject", status_code=200)
async def reject_run(
    run_id: str,
    authorization: Optional[str] = Header(None),
    sess: AsyncSession = Depends(get_session),
) -> dict:
    """HITL reject — records the decision; no downstream fire."""
    _require_proxy_key(authorization)
    return await _record_hitl_decision(sess, run_id, "rejected")
