"""Agent registry — the single source of truth for "what agents does AIPP
have and what can each of them do?".

Why this exists:
  - Before this file, agents were hard-wired in `orchestrator/graph.py` and
    the only way to know "what does agent X do?" was to read its source.
  - With this registry, any consumer (the UI, tests, an LLM, another agent)
    can call `list_agents()` at runtime and get a structured catalog.
  - `GET /api/agents` exposes this catalog to the frontend so an "About the
    agents" panel can be rendered without hardcoding anything.

How to add a new agent:
  1. Write the agent class in `backend/agents/<name>_agent.py`.
  2. Import it here.
  3. Call `register_agent(AgentSkill(...))` once at module import time.
  4. Add the node to `orchestrator/graph.py`.
"""

from __future__ import annotations

from typing import Dict, List

from backend.agents.skills import AgentSkill

_REGISTRY: Dict[str, AgentSkill] = {}


def register_agent(skill: AgentSkill) -> AgentSkill:
    """Register a skill. Idempotent — later calls with the same name win.

    Returns the skill so it can be used as a decorator-style expression:
        SKILL = register_agent(AgentSkill(...))
    """
    _REGISTRY[skill.name] = skill
    return skill


def list_agents() -> List[AgentSkill]:
    """Return all registered agents in registration order."""
    return list(_REGISTRY.values())


def get_agent(name: str) -> AgentSkill | None:
    """Look up one agent by name. `None` if unknown."""
    return _REGISTRY.get(name)


def registry_size() -> int:
    return len(_REGISTRY)


# --- Populate the registry at import time -----------------------------------
# We import agent modules lazily so this module can be imported by anything
# (tests, docs, UI) without triggering LLM client setup.
def _populate() -> None:
    from backend.models.pipeline import (
        ArchitectureProfile,
        GeneratedPipeline,
        PipelinePlan,
        TechnologyProfile,
    )
    from backend.models.environment import EnvironmentPlan
    from backend.models.rca import RCAReport
    from backend.models.repository import RepositoryAnalysis, RepositoryRequest
    from backend.models.validation import ValidationReport

    register_agent(AgentSkill(
        name="repository_analysis",
        label="Repository Analysis Agent",
        description="Reads the target repo through the GitHub MCP adapter and produces a structured RepositoryAnalysis.",
        skills=[
            "clone_repo_tree_read_only",
            "detect_dependency_files",
            "detect_dockerfiles_and_manifests",
            "detect_existing_ci_pipelines",
            "extract_readme_summary",
        ],
        inputs=RepositoryRequest,
        outputs=RepositoryAnalysis,
        reads_mcp=["github"],
        writes_mcp=[],
        depends_on=[],
        llm_backed=False,     # heuristics + optional LLM enrichment
    ))

    register_agent(AgentSkill(
        name="technology_detection",
        label="Technology Detection Agent",
        description="Infers language, framework, build tool, package manager, container/K8s/Helm readiness.",
        skills=[
            "detect_primary_language",
            "detect_framework",
            "detect_build_tool",
            "detect_package_manager",
            "detect_container_readiness",
        ],
        outputs=TechnologyProfile,
        depends_on=["repository_analysis"],
    ))

    register_agent(AgentSkill(
        name="architecture_detection",
        label="Architecture Detection Agent",
        description="Classifies the deployment shape (monolith / microservice / serverless / library / unknown).",
        skills=[
            "classify_architecture_style",
            "estimate_service_count",
            "list_entry_points",
            "list_databases_and_external_services",
        ],
        outputs=ArchitectureProfile,
        depends_on=["repository_analysis", "technology_detection"],
    ))

    register_agent(AgentSkill(
        name="pipeline_planning",
        label="Pipeline Planning Agent",
        description="Decides which stages the CI/CD pipeline should contain (build, test, scan, deploy, ...).",
        skills=[
            "select_required_stages",
            "resolve_stage_dependencies",
            "attach_tools_to_stages",
            "honour_pipeline_scope_directive",
        ],
        outputs=PipelinePlan,
        depends_on=["technology_detection", "architecture_detection"],
    ))

    register_agent(AgentSkill(
        name="environment_deployment",
        label="Environment Deployment Agent",
        description="Sets trigger + approval rules per environment (Dev / QA / Staging / Prod).",
        skills=[
            "define_environment_triggers",
            "assign_approval_gates",
            "choose_deployment_strategy",
            "enforce_production_manual_approval",
        ],
        outputs=EnvironmentPlan,
        depends_on=["pipeline_planning"],
    ))

    register_agent(AgentSkill(
        name="pipeline_generation",
        label="Pipeline Generation Agent",
        description="Turns the plan + environment rules into concrete YAML for the selected CI platform.",
        skills=[
            "render_platform_specific_yaml",
            "apply_deployment_target_hints",
            "emit_native_task_steps",
            "attach_inline_comments",
        ],
        outputs=GeneratedPipeline,
        depends_on=["pipeline_planning", "environment_deployment"],
        llm_backed=False,     # deterministic templates
    ))

    register_agent(AgentSkill(
        name="pipeline_validation",
        label="Pipeline Validation Agent",
        description="Runs 4 deterministic validators (YAML syntax, platform schema, security, environment rules) with self-healing retries.",
        skills=[
            "validate_yaml_syntax",
            "validate_platform_schema",
            "validate_security_policy",
            "validate_environment_rules",
            "self_healing_retry",
        ],
        outputs=ValidationReport,
        depends_on=["pipeline_generation"],
        llm_backed=False,
    ))

    register_agent(AgentSkill(
        name="pipeline_doctor_rca",
        label="Pipeline Doctor / RCA Agent",
        description="Parses failing CI/CD logs and produces a structured RCAReport grounded in real log lines.",
        skills=[
            "parse_failure_logs",
            "ground_evidence_in_log_line_numbers",
            "separate_evidence_from_ai_inference",
            "produce_corrective_and_preventive_actions",
            "confidence_calibration",
        ],
        outputs=RCAReport,
        reads_mcp=["github_actions", "gitlab", "harness", "tekton"],
        writes_mcp=[],
        depends_on=[],
    ))


_populate()
