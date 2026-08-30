"""n8n service — exposes list_workflows + last-execution for each."""

from __future__ import annotations

from datetime import datetime
from typing import List

from backend.core.exceptions import ToolNotConfiguredError
from backend.core.logging import get_logger
from backend.mcp.client import get_mcp_client
from backend.models.workflow import N8nStatusResponse, N8nWorkflowStatus

logger = get_logger(__name__)


def _first_env_tag(tags: list) -> str | None:
    for t in tags or []:
        name = t.get("name") if isinstance(t, dict) else str(t)
        if name and name.lower() in {"development", "qa", "staging", "production"}:
            return name.lower()
    return None


class N8nService:
    async def status(self) -> N8nStatusResponse:
        mcp = get_mcp_client()
        if not mcp.is_configured("n8n"):
            return N8nStatusResponse(
                configured=False,
                reason="N8N_BASE_URL and N8N_API_KEY are not set in .env — configure n8n to see workflows.",
            )
        try:
            workflows = await mcp.call("n8n", "list_workflows")
        except ToolNotConfiguredError as e:
            return N8nStatusResponse(configured=False, reason=str(e))
        except Exception as e:
            logger.warning("n8n api error: %s", e)
            return N8nStatusResponse(configured=False, reason=f"n8n API error: {e}")

        out: List[N8nWorkflowStatus] = []
        for w in workflows:
            wid = str(w.get("id"))
            tags = w.get("tags", [])
            last_exec_status = None
            last_exec_time = None
            success = None
            try:
                execs = await mcp.call("n8n", "get_executions", workflow_id=wid, limit=1)
                if execs:
                    e = execs[0]
                    raw_status = (e.get("status") or "").lower()
                    fin = e.get("finished")
                    has_error = bool(e.get("error")) or (raw_status == "error")

                    if raw_status:
                        last_exec_status = raw_status
                    else:
                        last_exec_status = "success" if fin else "running"

                    if e.get("stoppedAt"):
                        last_exec_time = datetime.fromisoformat(e["stoppedAt"].replace("Z", "+00:00"))
                    elif e.get("startedAt"):
                        last_exec_time = datetime.fromisoformat(e["startedAt"].replace("Z", "+00:00"))

                    if raw_status == "success":
                        success = True
                    elif raw_status in ("error", "canceled") or has_error:
                        success = False
                    elif raw_status in ("running", "waiting"):
                        success = None
                    elif fin is True:
                        success = not has_error
                    elif fin is False:
                        success = False
            except Exception:
                pass
            out.append(N8nWorkflowStatus(
                id=wid,
                name=w.get("name", "(unnamed)"),
                active=bool(w.get("active", False)),
                trigger_type=(w.get("nodes", [{}])[0] or {}).get("type") if w.get("nodes") else None,
                environment=_first_env_tag(tags),
                last_execution_status=last_exec_status,
                last_execution_time=last_exec_time,
                success=success,
                tags=[t.get("name") if isinstance(t, dict) else str(t) for t in tags],
            ))
        return N8nStatusResponse(configured=True, workflows=out)
