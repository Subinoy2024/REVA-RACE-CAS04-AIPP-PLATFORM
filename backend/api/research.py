"""Research + audit endpoints — read-only helpers for the evaluation dashboard.

Also hosts the **Batch Repo Runner** (`POST /api/research/batch`) used by the
Gradio Batch Runner tab and the thesis benchmark scripts. It walks a list of
repositories, generates a pipeline for each, records a `ResearchExperiment`
row with per-repo metrics, and returns an aggregate + per-repo breakdown that
the UI renders as a table plus CSV download.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import AIPPError, LLMError
from backend.core.logging import get_logger
from backend.database.connection import get_session, session_scope
from backend.database.models import AuditLog, PipelineRun, RCAReport, ResearchExperiment
from backend.models.pipeline import CIPlatform, CloudPlatform, DeploymentTarget
from backend.models.repository import RepositoryRequest
from backend.services.pipeline_service import PipelineService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


class ExperimentIn(BaseModel):
    experiment_type: str  # e.g. "static_template" | "generic_llm" | "aipp"
    ci_platform: Optional[str] = None
    repository_url: Optional[str] = None
    metrics: dict[str, Any] = {}
    notes: Optional[str] = None


@router.get("/audit")
async def audit(limit: int = 50, sess: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await sess.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))).scalars().all()
    return [
        {
            "id": str(r.id), "action": r.action, "actor": r.actor, "tool": r.tool,
            "details": r.details_json, "created_at": r.created_at.isoformat(),
        } for r in rows
    ]


@router.get("/metrics")
async def metrics(sess: AsyncSession = Depends(get_session)) -> dict:
    total_runs = (await sess.execute(select(func.count(PipelineRun.id)))).scalar_one()
    total_rca = (await sess.execute(select(func.count(RCAReport.id)))).scalar_one()
    avg_gen = (await sess.execute(select(func.avg(PipelineRun.generation_seconds)))).scalar_one() or 0
    avg_conf = (await sess.execute(select(func.avg(RCAReport.confidence)))).scalar_one() or 0
    return {
        "pipeline_runs": total_runs,
        "rca_reports": total_rca,
        "avg_generation_seconds": float(avg_gen or 0),
        "avg_rca_confidence": float(avg_conf or 0),
    }


@router.post("/experiments")
async def add_experiment(body: ExperimentIn) -> dict:
    async with session_scope() as sess:
        row = ResearchExperiment(
            experiment_type=body.experiment_type,
            ci_platform=body.ci_platform,
            repository_url=body.repository_url,
            metrics_json=body.metrics,
            notes=body.notes,
        )
        sess.add(row)
        await sess.flush()
        return {"id": str(row.id)}


@router.get("/experiments")
async def list_experiments(sess: AsyncSession = Depends(get_session), limit: int = 100) -> list[dict]:
    rows = (await sess.execute(select(ResearchExperiment).order_by(ResearchExperiment.created_at.desc()).limit(limit))).scalars().all()
    return [
        {
            "id": str(r.id),
            "experiment_type": r.experiment_type,
            "ci_platform": r.ci_platform,
            "repository_url": r.repository_url,
            "metrics": r.metrics_json,
            "notes": r.notes,
            "created_at": r.created_at.isoformat(),
        } for r in rows
    ]



# ---------------------------------------------------------------------------
# Iteration-26 · Batch Repo Runner
# ---------------------------------------------------------------------------
# Runs pipeline generation across a list of GitHub repos with a common
# configuration and records a ResearchExperiment row for each. Used by the
# Gradio Batch Runner tab to build the MS-thesis benchmark table.
# ---------------------------------------------------------------------------


class BatchRepoItem(BaseModel):
    repo_url: HttpUrl
    branch: str = "main"


class BatchRunRequest(BaseModel):
    repos: list[BatchRepoItem] = Field(..., min_length=1, max_length=20)
    github_pat: str = Field(..., min_length=8)
    ci_platform: CIPlatform
    cloud_platform: CloudPlatform
    pipeline_type: str = "all_in_one"
    iac_tool: str = "terraform"
    deployment_target: DeploymentTarget = DeploymentTarget.unspecified
    experiment_label: str = "aipp"  # tags ResearchExperiment rows for filtering


class BatchRepoResult(BaseModel):
    repo_url: str
    branch: str
    status: str                    # "ok" | "error"
    seconds: float
    validation_passed: Optional[bool] = None
    yaml_bytes: int = 0
    secrets_clean: Optional[bool] = None
    deployment_target: Optional[str] = None
    run_id: Optional[str] = None
    experiment_id: Optional[str] = None
    error: Optional[str] = None


class BatchRunResponse(BaseModel):
    total: int
    ok: int
    failed: int
    avg_seconds: float
    total_seconds: float
    results: list[BatchRepoResult]


@router.post("/batch", response_model=BatchRunResponse)
async def run_batch(body: BatchRunRequest) -> BatchRunResponse:
    """Generate a pipeline for each repo and record one ResearchExperiment per row.

    Repos are processed **sequentially** so that LLM rate limits are honoured
    and the audit log stays chronologically ordered. Per-repo failures are
    captured and reported instead of aborting the batch.
    """
    service = PipelineService()
    results: list[BatchRepoResult] = []
    batch_started = time.perf_counter()

    for item in body.repos:
        repo_url_str = str(item.repo_url)
        r_started = time.perf_counter()
        try:
            req = RepositoryRequest(
                repo_url=item.repo_url,
                github_pat=body.github_pat,
                branch=item.branch,
            )
            gen = await service.generate(
                req=req,
                ci_platform=body.ci_platform,
                cloud_platform=body.cloud_platform,
                custom_requirement="",
                pipeline_type=body.pipeline_type,
                agent_pool=None,
                iac_tool=body.iac_tool,
                deployment_target=body.deployment_target.value,
            )
            elapsed = time.perf_counter() - r_started
            yaml_body = (gen.get("pipeline") or {}).get("yaml_content", "") or ""
            validation_passed = bool(gen.get("validation", {}).get("passed", False))
            secrets_clean = bool(gen.get("security_scan", {}).get("clean", True))
            metrics = {
                "seconds": round(elapsed, 3),
                "validation_passed": validation_passed,
                "yaml_bytes": len(yaml_body.encode("utf-8")),
                "secrets_clean": secrets_clean,
                "deployment_target": gen.get("deployment_target")
                or body.deployment_target.value,
                "cloud": body.cloud_platform.value,
                "pipeline_type": body.pipeline_type,
                "iac_tool": body.iac_tool,
                "run_id": gen.get("run_id"),
            }
            async with session_scope() as sess:
                row = ResearchExperiment(
                    experiment_type=body.experiment_label,
                    ci_platform=body.ci_platform.value,
                    repository_url=repo_url_str,
                    metrics_json=metrics,
                    notes=f"batch pipeline_type={body.pipeline_type}",
                )
                sess.add(row)
                await sess.flush()
                experiment_id = str(row.id)
            results.append(BatchRepoResult(
                repo_url=repo_url_str,
                branch=item.branch,
                status="ok",
                seconds=round(elapsed, 3),
                validation_passed=validation_passed,
                yaml_bytes=len(yaml_body.encode("utf-8")),
                secrets_clean=secrets_clean,
                deployment_target=metrics["deployment_target"],
                run_id=gen.get("run_id"),
                experiment_id=experiment_id,
            ))
        except (LLMError, AIPPError, HTTPException) as e:
            elapsed = time.perf_counter() - r_started
            msg = getattr(e, "detail", None) or str(e)
            logger.warning("batch repo failed", extra={"repo": repo_url_str, "err": msg})
            async with session_scope() as sess:
                row = ResearchExperiment(
                    experiment_type=body.experiment_label,
                    ci_platform=body.ci_platform.value,
                    repository_url=repo_url_str,
                    metrics_json={"seconds": round(elapsed, 3), "error": str(msg)},
                    notes="batch failure",
                )
                sess.add(row)
                await sess.flush()
                experiment_id = str(row.id)
            results.append(BatchRepoResult(
                repo_url=repo_url_str,
                branch=item.branch,
                status="error",
                seconds=round(elapsed, 3),
                experiment_id=experiment_id,
                error=str(msg),
            ))
        except Exception as e:  # unexpected — record & continue
            elapsed = time.perf_counter() - r_started
            logger.exception("batch repo crashed", extra={"repo": repo_url_str})
            results.append(BatchRepoResult(
                repo_url=repo_url_str,
                branch=item.branch,
                status="error",
                seconds=round(elapsed, 3),
                error=str(e),
            ))
        # Small yield so long batches don't starve the event loop.
        await asyncio.sleep(0)

    total_seconds = time.perf_counter() - batch_started
    ok = sum(1 for r in results if r.status == "ok")
    ok_times = [r.seconds for r in results if r.status == "ok"]
    avg = round(sum(ok_times) / len(ok_times), 3) if ok_times else 0.0
    return BatchRunResponse(
        total=len(results),
        ok=ok,
        failed=len(results) - ok,
        avg_seconds=avg,
        total_seconds=round(total_seconds, 3),
        results=results,
    )
