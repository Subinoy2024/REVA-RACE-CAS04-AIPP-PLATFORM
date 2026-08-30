"""AIPP LangGraph orchestrator.

Assembles the sequence of agents into a StateGraph. Kept intentionally linear
for the MS-research first iteration — branching (e.g. skipping SAST for a
library) can be added by inserting conditional edges later.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from langgraph.graph import END, StateGraph

from backend.agents.architecture_agent import ArchitectureDetectionAgent
from backend.agents.deployment_agent import EnvironmentDeploymentAgent
from backend.agents.pipeline_generator import PipelineGenerationAgent
from backend.agents.pipeline_planner import PipelinePlanningAgent
from backend.agents.repository_agent import RepositoryAnalysisAgent
from backend.agents.technology_agent import TechnologyDetectionAgent
from backend.agents.validation_agent import PipelineValidationAgent
from backend.core.logging import get_logger
from backend.mcp.client import get_mcp_client
from backend.models.pipeline import (
    ArchitectureProfile,
    CIPlatform,
    CloudPlatform,
    PipelinePlan,
    TechnologyProfile,
)
from backend.models.environment import EnvironmentPlan
from backend.models.repository import RepositoryAnalysis, RepositoryRequest
from backend.orchestrator import progress
from backend.orchestrator.state import AIPPState

logger = get_logger(__name__)


# Order matters — index used to render progress bars in the UI.
AGENT_ORDER = [
    ("repository_analysis", "Repository analysis"),
    ("technology_detection", "Technology detection"),
    ("architecture_detection", "Architecture detection"),
    ("pipeline_planning", "Pipeline planning"),
    ("environment_deployment", "Environment strategy"),
    ("pipeline_generation", "Pipeline YAML generation"),
    ("pipeline_validation", "Validation"),
]
_AGENT_INDEX = {name: (i, label) for i, (name, label) in enumerate(AGENT_ORDER)}
TOTAL_AGENTS = len(AGENT_ORDER)


def _track(agent: str, inner: Callable[[AIPPState], Awaitable[AIPPState]]):
    """Wrap a node to emit `running` before + `done`/`failed` after.

    Also opens an agent-scoped `TraceCollector` (iteration-27) so any LLM
    call or MCP invocation made inside the node is recorded against the
    run's `agent_traces` bucket. The collector is finalised on exit and
    one row is INSERTed into `agent_traces`.
    """
    idx, label = _AGENT_INDEX[agent]

    async def wrapped(state: AIPPState) -> AIPPState:
        sid = state.get("stream_id")
        run_id_str = state.get("run_id")
        # Trace collector — only opened when we know the run_id (i.e. the
        # workflow was launched via PipelineService.generate). Direct
        # LangGraph invocations from tests may skip it.
        from backend.services.agent_trace import TraceCollector, bind as _trace_bind
        import uuid as _uuid
        collector: TraceCollector | None = None
        if run_id_str:
            try:
                collector = TraceCollector(
                    run_id=_uuid.UUID(run_id_str),
                    agent_name=agent,
                    step_index=idx,
                )
            except (ValueError, TypeError):
                collector = None

        # Snapshot the input state keys BEFORE running the agent — the
        # inner node returns *only* the delta (new keys), and we want to
        # remember what the agent had access to.
        input_snapshot = {k: state.get(k) for k in state.keys()} if isinstance(state, dict) else {}

        await progress.publish(
            sid, agent=agent, status="running", detail=f"{label} started",
            total_agents=TOTAL_AGENTS, agent_index=idx,
        )

        # Nested context managers — order matters (trace outermost so LLM
        # / MCP calls inside the agent see it; stream_id + agent name are
        # per-node concerns).
        try:
            from backend.mcp.guard import bind_agent as _bind_agent
            _outer = _trace_bind(collector) if collector is not None else None
            if _outer is not None:
                _outer.__enter__()
            try:
                with progress.bind_stream_id(sid), _bind_agent(agent):
                    out = await inner(state)
            finally:
                pass
        except Exception as e:
            if collector is not None:
                collector.mark_error(e)
                try:
                    await collector.finalize(input_snapshot=input_snapshot, output_snapshot={})
                except Exception:                                  # noqa: BLE001
                    logger.debug("agent_trace: finalize on error path failed", exc_info=True)
            if _outer is not None:
                _outer.__exit__(type(e), e, e.__traceback__)
            await progress.publish(
                sid, agent=agent, status="failed", detail=str(e)[:200],
                kind="error", total_agents=TOTAL_AGENTS, agent_index=idx,
            )
            raise

        if collector is not None:
            try:
                await collector.finalize(
                    input_snapshot=input_snapshot,
                    output_snapshot=out if isinstance(out, dict) else {},
                )
            except Exception:                                      # noqa: BLE001
                logger.debug("agent_trace: finalize failed", exc_info=True)
            if _outer is not None:
                _outer.__exit__(None, None, None)

        await progress.publish(
            sid, agent=agent, status="done", detail=f"{label} complete",
            total_agents=TOTAL_AGENTS, agent_index=idx,
        )
        return out

    return wrapped


def build_graph() -> StateGraph:
    graph = StateGraph(AIPPState)

    mcp = get_mcp_client()
    repo_agent = RepositoryAnalysisAgent(mcp)
    tech_agent = TechnologyDetectionAgent()
    arch_agent = ArchitectureDetectionAgent()
    plan_agent = PipelinePlanningAgent()
    env_agent = EnvironmentDeploymentAgent()
    gen_agent = PipelineGenerationAgent()
    val_agent = PipelineValidationAgent()

    async def node_repo(state: AIPPState) -> AIPPState:
        req = RepositoryRequest(
            repo_url=state["repo_url"], github_pat=state["github_pat"], branch=state.get("branch", "main"),
        )
        analysis = await repo_agent.run(req)
        return {"analysis": analysis.model_dump()}

    async def node_tech(state: AIPPState) -> AIPPState:
        analysis = RepositoryAnalysis.model_validate(state["analysis"])
        tech = await tech_agent.run(analysis=analysis)
        return {"tech": tech.model_dump()}

    async def node_arch(state: AIPPState) -> AIPPState:
        analysis = RepositoryAnalysis.model_validate(state["analysis"])
        tech = TechnologyProfile.model_validate(state["tech"])
        arch = await arch_agent.run(analysis=analysis, tech=tech)
        return {"architecture": arch.model_dump()}

    async def node_plan(state: AIPPState) -> AIPPState:
        analysis = RepositoryAnalysis.model_validate(state["analysis"])
        tech = TechnologyProfile.model_validate(state["tech"])
        arch = ArchitectureProfile.model_validate(state["architecture"])
        plan = await plan_agent.run(
            analysis=analysis, tech=tech, arch=arch,
            ci=CIPlatform(state["ci_platform"]),
            cloud=CloudPlatform(state["cloud_platform"]),
            custom_requirement=state.get("custom_requirement", ""),
            iac_tool=state.get("iac_tool", "terraform"),
        )
        return {"plan": plan.model_dump()}

    async def node_env(state: AIPPState) -> AIPPState:
        plan = PipelinePlan.model_validate(state["plan"])
        envp = await env_agent.run(plan=plan)
        return {"environments": envp.model_dump()}

    async def node_gen(state: AIPPState) -> AIPPState:
        plan = PipelinePlan.model_validate(state["plan"])
        envp = EnvironmentPlan.model_validate(state["environments"])
        tech = TechnologyProfile.model_validate(state["tech"])
        analysis = RepositoryAnalysis.model_validate(state["analysis"])
        pipeline = gen_agent.run(
            plan=plan, env_plan=envp, tech=tech, repo_name=analysis.name,
            pipeline_type=state.get("pipeline_type", "all_in_one"),
            agent_pool=state.get("agent_pool"),
            custom_requirement=state.get("custom_requirement", ""),
        )
        return {"pipeline": pipeline.model_dump()}

    async def node_validate(state: AIPPState) -> AIPPState:
        from backend.models.pipeline import GeneratedPipeline
        pipeline = GeneratedPipeline.model_validate(state["pipeline"])
        envp = EnvironmentPlan.model_validate(state["environments"])
        report = val_agent.run(pipeline=pipeline, env_plan=envp)
        return {"validation": report}

    graph.add_node("repository_analysis", _track("repository_analysis", node_repo))
    graph.add_node("technology_detection", _track("technology_detection", node_tech))
    graph.add_node("architecture_detection", _track("architecture_detection", node_arch))
    graph.add_node("pipeline_planning", _track("pipeline_planning", node_plan))
    graph.add_node("environment_deployment", _track("environment_deployment", node_env))
    graph.add_node("pipeline_generation", _track("pipeline_generation", node_gen))
    graph.add_node("pipeline_validation", _track("pipeline_validation", node_validate))

    graph.set_entry_point("repository_analysis")
    graph.add_edge("repository_analysis", "technology_detection")
    graph.add_edge("technology_detection", "architecture_detection")
    graph.add_edge("architecture_detection", "pipeline_planning")
    graph.add_edge("pipeline_planning", "environment_deployment")
    graph.add_edge("environment_deployment", "pipeline_generation")
    graph.add_edge("pipeline_generation", "pipeline_validation")
    graph.add_edge("pipeline_validation", END)
    return graph
