"""API endpoint — root-cause analysis over uploaded CI/CD logs."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from backend.core.exceptions import LLMError, RCAError
from backend.core.logging import get_logger
from backend.core.rate_limit import enforce_rca_limit
from backend.core.security import sha256, validate_upload
from backend.database.connection import get_session, session_scope
from backend.database.models import RCAReport
from backend.orchestrator.workflows import run_rca
from backend.services import rca_embedding_service

router = APIRouter(prefix="/api/pipeline-doctor", tags=["pipeline-doctor"])
logger = get_logger(__name__)


@router.post("/analyze")
async def analyze(
    request: Request,
    ci_platform: str = Form(...),
    incident_context: Optional[str] = Form(""),
    raw_log: Optional[str] = Form(None),
    log_file: Optional[UploadFile] = File(None),
) -> dict:
    enforce_rca_limit(request)
    if not raw_log and not log_file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide raw_log or log_file")

    if log_file is not None:
        content = await log_file.read()
        try:
            validate_upload(log_file.filename or "log.txt", len(content))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        log_text = content.decode("utf-8", errors="ignore")
    else:
        log_text = raw_log or ""

    if len(log_text.strip()) < 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="log too short for meaningful RCA")

    # ------------------------------------------------------------------
    # RAG step — before hitting the LLM, retrieve past RCAs cosine-close
    # to the current log so PipelineDoctor can reason with prior art.
    # Best-effort: retrieval failures never block a fresh RCA, they just
    # yield an empty context block.
    # ------------------------------------------------------------------
    # We embed a compact query (context + first ~2 KB of the log) — full
    # logs are too long for the embedding model and mostly noise.
    retrieval_query = (
        (incident_context or "").strip()
        + "\n"
        + " ".join(log_text.split()[:400])
    )[:4000]
    similar = await rca_embedding_service.find_similar(retrieval_query, limit=3)
    context_block = rca_embedding_service.format_context_block(similar)
    augmented_context = (
        context_block + "\n\n" + (incident_context or "")
    ).strip() if context_block else (incident_context or None)

    try:
        report = await run_rca(
            ci_platform=ci_platform, log_text=log_text,
            incident_context=augmented_context or None,
        )
    except LLMError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LLM error: {e}")
    except RCAError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # persist
    try:
        confidence = float(report.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    async with session_scope() as sess:
        row = RCAReport(
            ci_platform=ci_platform,
            log_sha256=sha256(log_text),
            log_bytes=len(log_text.encode("utf-8")),
            incident_context=incident_context or None,
            report_json=report,
            confidence=confidence,
        )
        sess.add(row)
        await sess.flush()
        report_id = str(row.id)

    # ------------------------------------------------------------------
    # Feed the new RCA back into the memory. Fire-and-forget — RCA save
    # already succeeded, this is pure enrichment.
    # ------------------------------------------------------------------
    try:
        await rca_embedding_service.embed_and_persist(report_id, report)
    except Exception as e:                                          # noqa: BLE001
        logger.info("rca_embed: post-analyze hook failed: %s", e)

    report["id"] = report_id
    # Surface which past incidents (if any) informed this RCA so
    # operators can trust-but-verify the retrieval was relevant.
    if similar:
        report["retrieved_from_memory"] = [
            {"rca_id": s["rca_id"], "similarity": s["similarity"],
             "root_cause": s.get("root_cause")}
            for s in similar
        ]
    return report


@router.get("/reports")
async def list_reports(limit: int = 20, sess: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await sess.execute(select(RCAReport).order_by(RCAReport.created_at.desc()).limit(limit))).scalars().all()
    return [
        {
            "id": str(r.id),
            "ci_platform": r.ci_platform,
            "confidence": r.confidence,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/reports/{report_id}")
async def get_report(report_id: str, sess: AsyncSession = Depends(get_session)) -> dict:
    row = (await sess.execute(select(RCAReport).where(RCAReport.id == report_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="report not found")
    return {
        "id": str(row.id),
        "ci_platform": row.ci_platform,
        "log_sha256": row.log_sha256,
        "log_bytes": row.log_bytes,
        "incident_context": row.incident_context,
        "confidence": row.confidence,
        "report": row.report_json,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/similar")
async def similar_rca_reports(q: str, limit: int = 5) -> dict:
    """Cosine-similarity search over PipelineDoctor's RCA memory.

    Returns the `limit` past incidents whose root-cause + corrective
    actions are closest to query string `q`. Same shape as
    `/api/pipelines/similar` but hitting `rca_embeddings` × `rca_reports`
    instead of the pipeline-side tables.

    Useful for:
      * on-call engineers pasting a fresh error message to see if AIPP
        has seen it before,
      * evaluating retrieval quality during MS defense (does semantic
        search actually surface the OOMKill history?).

    Falls back to an empty list when pgvector is not enabled — matches
    the behaviour of the pipeline-similar endpoint.
    """
    if not q or not q.strip():
        raise HTTPException(400, "q parameter is required")
    if limit < 1 or limit > 25:
        raise HTTPException(400, "limit must be 1..25")
    hits = await rca_embedding_service.find_similar(q.strip(), limit=limit)
    return {"query": q, "hits": len(hits), "results": hits}
