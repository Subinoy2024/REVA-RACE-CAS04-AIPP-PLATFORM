"""RCA embedding service — auto-populate `rca_embeddings` from every
successful RCAReport so PipelineDoctor learns from past incidents.

Iteration-34 shipped the schema (`rca_embeddings` with pgvector) and
migration but nothing wrote to it — PipelineDoctor started fresh every
call. This module closes the loop:

  • `embed_and_persist()` runs after every `/api/pipeline-doctor/analyze`
    call — turns the RCA's root cause + evidence + corrective actions
    into one `content` string, embeds it via `EmbeddingService`, and
    inserts a row in `rca_embeddings`.

  • `find_similar()` runs BEFORE the LLM call — retrieves top-K past
    RCAs cosine-closest to the new log and returns them so the caller
    can inject them as few-shot context. Result: on the 100th
    OOMKill in production, PipelineDoctor sees the previous 99 first.

Both functions degrade gracefully:
  * pgvector not installed → we swallow the error, return [] / skip
    insert, and log at INFO. RCA still works, just no learning.
  * embedding service returns the deterministic fallback vector when
    no LLM key is configured — retrieval quality drops but everything
    still runs.

Never persists raw log content — only the RCA's own summary text.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text as sa_text

from backend.core.logging import get_logger
from backend.database.connection import session_scope
from backend.services.embedding_service import EmbeddingService

logger = get_logger(__name__)


def _build_content(report_json: dict[str, Any]) -> str:
    """Compose the searchable-text field from the structured RCA.

    We concatenate the fields an operator would grep for when trying to
    find a similar past incident: root cause first (highest signal),
    then the failing stage, then the corrective and preventive
    actions. Evidence snippets are intentionally left OUT — they may
    contain project-specific paths/IPs that would poison retrieval.
    """
    lines: list[str] = []
    if rc := report_json.get("root_cause"):
        lines.append(f"Root cause: {rc}")
    if fs := report_json.get("failed_stage"):
        lines.append(f"Failed stage: {fs}")
    if ci := report_json.get("ci_platform"):
        lines.append(f"CI platform: {ci}")
    for label in ("corrective_actions", "preventive_actions",
                  "ai_inferences"):
        items = report_json.get(label) or []
        if items:
            lines.append(f"{label.replace('_', ' ').title()}:")
            for it in items:
                lines.append(f"  - {it}")
    return "\n".join(lines).strip() or "(empty rca)"


async def embed_and_persist(rca_id: str, report_json: dict[str, Any],
                            svc: EmbeddingService | None = None) -> bool:
    """Embed the RCA's content and insert a row into `rca_embeddings`.

    Returns True on success, False if we skipped (pgvector missing or
    insertion failed). Never raises — callers rely on this as a
    fire-and-forget audit hook.
    """
    content = _build_content(report_json)
    svc = svc or EmbeddingService()
    try:
        vec = await svc.embed(content)
    except Exception as e:                                          # noqa: BLE001
        logger.warning("rca_embed: embed call failed: %s", e)
        return False

    # pgvector expects a bracketed literal — same shape used by the
    # existing pipeline_embeddings insert in pipeline_service.py.
    vec_literal = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
    try:
        async with session_scope() as sess:
            await sess.execute(
                sa_text("""
                    INSERT INTO rca_embeddings (rca_id, content, embedding)
                    VALUES (:rid, :ct, CAST(:vec AS vector))
                """),
                {"rid": rca_id, "ct": content, "vec": vec_literal},
            )
            await sess.commit()
        logger.info("rca_embed: persisted rca_id=%s (%d chars)",
                    rca_id, len(content))
        return True
    except Exception as e:                                          # noqa: BLE001
        # Table missing, pgvector extension not enabled, or DB offline —
        # the whole system stays functional either way.
        logger.info("rca_embed: skipped rca_id=%s: %s", rca_id, e)
        return False


async def find_similar(query_text: str, limit: int = 3,
                       svc: EmbeddingService | None = None,
                       ) -> list[dict[str, Any]]:
    """Return the top-K past RCAs cosine-closest to `query_text`.

    Result shape:
      [
        {
          "rca_id": "<uuid>",
          "ci_platform": "<...>",
          "root_cause": "<from report_json>",
          "confidence": <float>,
          "created_at": "<iso>",
          "similarity": <float in 0..1>,
          "content_preview": "<first 400 chars of the stored content>"
        }
      ]

    Returns [] when pgvector is unavailable or the table is empty — the
    caller can safely treat that as "no relevant past incidents".
    """
    if not query_text.strip():
        return []
    if limit < 1:
        limit = 1
    if limit > 25:
        limit = 25

    svc = svc or EmbeddingService()
    try:
        qvec = await svc.embed(query_text)
    except Exception as e:                                          # noqa: BLE001
        logger.warning("rca_similar: embed failed: %s", e)
        return []
    vec_literal = "[" + ",".join(f"{v:.6f}" for v in qvec) + "]"

    try:
        async with session_scope() as sess:
            result = await sess.execute(
                sa_text("""
                    SELECT
                      re.rca_id::text                                  AS rca_id,
                      re.content                                       AS content,
                      rr.ci_platform                                   AS ci_platform,
                      rr.confidence                                    AS confidence,
                      rr.report_json                                   AS report_json,
                      rr.created_at                                    AS created_at,
                      (1 - (re.embedding <=> CAST(:qvec AS vector)))   AS similarity
                    FROM rca_embeddings re
                    JOIN rca_reports rr ON rr.id = re.rca_id
                    ORDER BY re.embedding <=> CAST(:qvec AS vector)
                    LIMIT :lim
                """),
                {"qvec": vec_literal, "lim": limit},
            )
            rows = result.mappings().all()
    except Exception as e:                                          # noqa: BLE001
        logger.info("rca_similar: query failed (pgvector missing?): %s", e)
        return []

    out: list[dict[str, Any]] = []
    for r in rows:
        rj = r["report_json"] or {}
        out.append({
            "rca_id": r["rca_id"],
            "ci_platform": r["ci_platform"],
            "root_cause": rj.get("root_cause"),
            "failed_stage": rj.get("failed_stage"),
            "confidence": float(r["confidence"] or 0.0),
            "similarity": round(float(r["similarity"] or 0.0), 4),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "content_preview": (r["content"] or "")[:400],
        })
    return out


def format_context_block(similar: list[dict[str, Any]]) -> str:
    """Turn `find_similar()` results into a text block suitable for
    prepending to `incident_context` on the LLM call.

    Empty input → empty string (so the RCA prompt looks like it always
    did when there's no history to draw on).
    """
    if not similar:
        return ""
    lines = [
        "Past similar incidents (retrieved automatically from AIPP's "
        "RCA memory — use as prior evidence, but do NOT cite them as "
        "log evidence for the current incident):",
    ]
    for i, s in enumerate(similar, start=1):
        lines.append(
            f"  {i}. [{s.get('ci_platform', '?')} · "
            f"similarity {s.get('similarity', 0.0):.2f}] "
            f"{s.get('root_cause') or '(no root cause captured)'}"
        )
    return "\n".join(lines)
