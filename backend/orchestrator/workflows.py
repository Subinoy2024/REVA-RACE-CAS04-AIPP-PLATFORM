"""High-level workflows callable from FastAPI routes and services."""

from __future__ import annotations

from typing import Any, Dict

from backend.agents.rca_agent import PipelineDoctorAgent
from backend.core.logging import get_logger
from backend.core.security import sanitize_repository_snippet
from backend.models.pipeline import CIPlatform, CloudPlatform
from backend.models.repository import RepositoryRequest
from backend.orchestrator.graph import build_graph

logger = get_logger(__name__)


async def run_pipeline_generation(
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
    run_id: str | None = None,
) -> Dict[str, Any]:
    graph = build_graph().compile()
    # Iteration-21: if user picked a concrete deployment target, prepend a
    # deterministic directive so the LLM planner uses it verbatim. Keeps the
    # LLM out of the "target guessing" business.
    if deployment_target and deployment_target != "unspecified":
        target_directive = (
            f"DEPLOYMENT TARGET (user-selected, MUST honour): {deployment_target}. "
            f"Emit deploy stages that specifically target this service. "
            f"Do NOT substitute a different target on the same cloud."
        )
        custom_requirement = f"{target_directive}\n\n{custom_requirement or ''}".strip()

    initial = {
        "repo_url": str(req.repo_url),
        "github_pat": req.github_pat,
        "branch": req.branch,
        "ci_platform": ci_platform.value,
        "cloud_platform": cloud_platform.value,
        "custom_requirement": sanitize_repository_snippet(custom_requirement or "", max_chars=1500),
        "stream_id": stream_id,
        "pipeline_type": pipeline_type or "all_in_one",
        "agent_pool": agent_pool,
        "iac_tool": (iac_tool or "terraform").strip().lower(),
        "deployment_target": deployment_target or "unspecified",
        "run_id": run_id,
    }
    final = await graph.ainvoke(initial)
    explanation = _build_explanation(final)
    final["explanation"] = explanation
    # PAT + stream_id were passed through state; scrub before returning.
    final.pop("github_pat", None)
    final.pop("stream_id", None)
    return final


async def run_rca(*, ci_platform: str, log_text: str, incident_context: str | None) -> dict:
    agent = PipelineDoctorAgent()
    report = await agent.run(
        ci_platform=ci_platform,
        log_text=log_text,
        incident_context=incident_context,
    )
    return report.model_dump(mode="json")


# ---------- helpers ----------
def _build_explanation(state: Dict[str, Any]) -> str:
    a = state.get("analysis") or {}
    t = state.get("tech") or {}
    ar = state.get("architecture") or {}
    p = state.get("plan") or {}
    envp = state.get("environments") or {}
    v = state.get("validation") or {}

    lines = [
        f"Repository: {a.get('owner')}/{a.get('name')} @ {a.get('branch')}",
        f"Technology: {t.get('language')} / {t.get('framework')} (build: {t.get('build_tool')}, tests: {t.get('test_framework')})",
        f"Architecture: {ar.get('style')} (~{ar.get('service_count_estimate')} service(s))",
        "",
        "Pipeline stages selected:",
    ]
    for s in p.get("stages", []):
        lines.append(f"  • {s['name']} — {s.get('explanation','')}")
    lines.append("")
    lines.append("Environment strategy:")
    for r in envp.get("rules", []):
        lines.append(f"  • {r['name']}: trigger={r['trigger']}, approval={r['requires_approval']}, "
                     f"strategy={r['deployment_strategy']} — {r.get('explanation','')}")
    lines.append("")
    if v:
        status = "PASSED" if v.get("passed") else "WARNINGS"
        lines.append(f"Validation: {status}")
        for c in v.get("checks", []):
            lines.append(f"  - {c['name']}: {'ok' if c['passed'] else 'FAIL'} — {c['detail']}")
    if p.get("custom_requirement_addressed"):
        lines.append("")
        lines.append(f"Custom requirement handled: {p['custom_requirement_addressed']}")
    return "\n".join(lines)
