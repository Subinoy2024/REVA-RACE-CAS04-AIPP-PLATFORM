"""Pipeline service — orchestrates a full end-to-end generation and persists the run."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from backend.core.logging import get_logger
from backend.database.connection import session_scope
from backend.database.models import PipelineRun
from backend.models.pipeline import CIPlatform, CloudPlatform
from backend.models.repository import RepositoryRequest
from backend.orchestrator.workflows import run_pipeline_generation
from backend.services.audit_service import AuditService

logger = get_logger(__name__)


class PipelineService:
    def __init__(self) -> None:
        self.audit = AuditService()

    async def generate(
        self,
        *,
        req: RepositoryRequest,
        ci_platform: CIPlatform,
        cloud_platform: CloudPlatform,
        custom_requirement: str,
        stream_id: str | None = None,
        pipeline_type: str = "all_in_one",
        agent_pool: str | None = None,
        iac_tool: str = "terraform",
        deployment_target: str = "unspecified",
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        # Iteration-27: pre-generate the run UUID so every agent trace row
        # created during the workflow can FK to the PipelineRun that will
        # be inserted at the end of this method.
        import uuid as _uuid
        run_id = str(_uuid.uuid4())
        await self.audit.log(action="pipeline.generate.start",
                             details={"ci": ci_platform.value, "cloud": cloud_platform.value,
                                      "iac_tool": iac_tool,
                                      "deployment_target": deployment_target,
                                      "run_id": run_id})
        try:
            result = await run_pipeline_generation(
                req=req, ci_platform=ci_platform, cloud_platform=cloud_platform,
                custom_requirement=custom_requirement,
                stream_id=stream_id,
                pipeline_type=pipeline_type,
                agent_pool=agent_pool,
                iac_tool=iac_tool,
                deployment_target=deployment_target,
                run_id=run_id,
            )
        except Exception as e:
            await self.audit.log(action="pipeline.generate.error",
                                 details={"error": str(e), "run_id": run_id})
            raise

        # Secret-scan the generated YAML *before* returning so the UI can
        # warn the user and the commit endpoint can hard-fail on findings.
        from backend.services.secret_scanner import scan_report as _secret_scan
        yaml_body = (result.get("pipeline") or {}).get("yaml_content", "")
        result["security_scan"] = _secret_scan(yaml_body)
        if not result["security_scan"]["clean"]:
            await self.audit.log(
                action="pipeline.generate.secrets_flagged",
                details={
                    "count": len(result["security_scan"]["findings"]),
                    "kinds": sorted({f["kind"] for f in result["security_scan"]["findings"]}),
                },
            )

        # Deployment-target hints: if the user picked a concrete target,
        # inject a header comment block into the YAML and append a
        # guidance section to the explanation. Skipped for `unspecified`.
        from backend.services.target_hints import (
            header_comment as _th_header,
            explanation_section as _th_section,
        )
        header = _th_header(deployment_target)
        if header:
            new_yaml = header + yaml_body
            result["pipeline"]["yaml_content"] = new_yaml
            result["explanation"] = (result.get("explanation") or "") + _th_section(deployment_target)
            result["deployment_target"] = deployment_target
            yaml_body = new_yaml

        elapsed = time.perf_counter() - started

        # -----------------------------------------------------------------
        # Directive trace — machine-checkable audit trail proving the
        # custom_requirement was recognised AND enforced in the YAML.
        # Shown as a collapsible panel in the UI so the user (or a thesis
        # reviewer) can verify without eyeballing every line of YAML.
        # -----------------------------------------------------------------
        from backend.generators.base import build_directive_trace as _build_trace
        result["directive_trace"] = _build_trace(
            custom_requirement=custom_requirement,
            yaml_text=result["pipeline"]["yaml_content"],
            llm_acknowledgement=(result.get("plan") or {}).get("custom_requirement_addressed"),
        )
        logger.info(
            "directive.trace status=%s recognised=%s deploy_style=%s "
            "az_cli=%s py_sdk=%s commit_scoped_image=%s",
            result["directive_trace"]["enforcement_status"],
            result["directive_trace"]["recognised"],
            result["directive_trace"]["deploy_style"],
            result["directive_trace"]["yaml_evidence"]["az_cli_task_count"],
            result["directive_trace"]["yaml_evidence"]["python_sdk_task_count"],
            result["directive_trace"]["yaml_evidence"]["commit_scoped_image"],
        )

        async with session_scope() as sess:
            row = PipelineRun(
                id=_uuid.UUID(run_id),
                repository_url=str(req.repo_url),
                branch=req.branch,
                ci_platform=ci_platform.value,
                cloud_platform=cloud_platform.value,
                custom_requirement=custom_requirement or None,
                analysis_json=result["analysis"],
                plan_json=result["plan"],
                environments_json=result["environments"],
                validation_json=result["validation"],
                yaml_output=result["pipeline"]["yaml_content"],
                explanation=result["explanation"],
                generation_seconds=elapsed,
                status="completed" if result["validation"]["passed"] else "completed_with_warnings",
            )
            sess.add(row)
            await sess.flush()

        await self.audit.log(action="pipeline.generate.done",
                             details={"run_id": run_id, "seconds": elapsed})

        # Fire HITL review gate on n8n workflow #16 — best-effort. Failure
        # to notify n8n never fails generation. Slack card includes the
        # approve/reject curl commands and downstream fan-out happens on
        # approve, not here.
        try:
            from backend.services.n8n_hooks import fire
            await fire("pipeline_review", {"body": {
                "run_id": run_id,
                "target_platform": result.get("plan", {}).get("target", "unknown"),
                "cloud": result.get("plan", {}).get("cloud", "unknown"),
                "repo": str(req.repo_url),
                "actor": "aipp-generator",
                "summary_url": f"/pipelines/runs/{run_id}",
            }})
        except Exception:                                        # noqa: BLE001
            pass

        # Embed the explanation into pgvector for future RAG retrieval
        # (`GET /api/pipelines/similar?q=...`). Best-effort — pgvector may
        # not be enabled on legacy DBs, in which case we skip silently and
        # the similarity endpoint returns an empty list.
        try:
            from sqlalchemy import text as sa_text
            from backend.services.embedding_service import EmbeddingService
            summary = (result.get("explanation") or "")[:8000]
            if summary.strip():
                svc = EmbeddingService()
                vec = await svc.embed(summary)
                vec_literal = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
                async with session_scope() as sess:
                    await sess.execute(
                        sa_text("""
                            INSERT INTO pipeline_embeddings (run_id, summary, embedding)
                            VALUES (:rid, :sm, CAST(:vec AS vector))
                        """),
                        {"rid": run_id, "sm": summary, "vec": vec_literal},
                    )
                    await sess.commit()
        except Exception as e:                                   # noqa: BLE001
            # pgvector not enabled or migration not applied — swallow
            import logging
            logging.getLogger(__name__).info(
                "embedding skipped for run %s: %s", run_id, e,
            )

        result["run_id"] = run_id
        result["generation_seconds"] = elapsed
        return result
