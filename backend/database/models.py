"""ORM models. One table per real domain entity — kept small and readable."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    branch: Mapped[str] = mapped_column(String(200), nullable=False, default="main")
    owner: Mapped[Optional[str]] = mapped_column(String(200))
    name: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    repository_url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    branch: Mapped[str] = mapped_column(String(200), nullable=False)
    ci_platform: Mapped[str] = mapped_column(String(64), nullable=False)
    cloud_platform: Mapped[str] = mapped_column(String(64), nullable=False)
    custom_requirement: Mapped[Optional[str]] = mapped_column(Text)

    analysis_json: Mapped[dict] = mapped_column(JSON, default=dict)
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict)
    environments_json: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    yaml_output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")

    generation_seconds: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class RCAReport(Base):
    __tablename__ = "rca_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    ci_platform: Mapped[str] = mapped_column(String(64), nullable=False)
    log_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    log_bytes: Mapped[int] = mapped_column(Integer, default=0)
    incident_context: Mapped[Optional[str]] = mapped_column(Text)
    report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    action: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    actor: Mapped[Optional[str]] = mapped_column(String(200))
    tool: Mapped[Optional[str]] = mapped_column(String(200))
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class ResearchExperiment(Base):
    __tablename__ = "research_experiments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    experiment_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ci_platform: Mapped[Optional[str]] = mapped_column(String(64))
    repository_url: Mapped[Optional[str]] = mapped_column(String(500))
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class LLMCall(Base):
    """One row per LLM invocation. Populated by `services.llm_usage`.

    Enables historical cost / token tracking across container restarts —
    the in-memory tracker resets on reboot, this table does not. Powers
    `GET /api/llm/usage/history` for the thesis Evaluation chapter.
    """
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    agent: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class DeploymentTarget(Base):
    """User-onboarded CI/CD platform where AIPP can auto-push generated YAML.

    Iteration-25 (Auto-Deploy): the "deployment repo" is separate from the
    analyzed source repo. Credentials are stored **Fernet-encrypted** in
    `token_encrypted` — the raw PAT never lands on disk or in logs.

    `platform` ∈ {`github_actions`, `azure_devops`}.
    `extra_json` holds platform-specific fields such as ADO
    org URL / project name.
    """
    __tablename__ = "deployment_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(200), nullable=False, default="main")
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    extra_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Deployment(Base):
    """One row per auto-deploy attempt. Audit trail for the Integrations tab."""
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    branch: Mapped[str] = mapped_column(String(200), nullable=False)
    ci_platform: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="pr")  # pr | commit
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")  # pending|success|failed
    commit_sha: Mapped[Optional[str]] = mapped_column(String(64))
    ref_url: Mapped[Optional[str]] = mapped_column(String(500))
    yaml_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class User(Base):
    """Application user (thesis-scope: single-tenant, no per-user data yet).

    The `is_default` flag identifies the auto-seeded admin account.
    When cloud-identity (OIDC / Google Workspace / Azure AD) is enabled
    via `POST /api/auth/oidc/enable`, the seeded default account is
    flipped to `is_active=False` so nobody can log in with the seeded
    password after the org's identity provider takes over.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32), default="admin")
    is_active: Mapped[bool] = mapped_column(default=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)



class SiteVisit(Base):
    """Iteration-26.5 · one row per landing on the app (login page load).

    Kept intentionally small — no PII, no cookies. The footer's visitor
    counter reads `SELECT COUNT(*) FROM site_visits;` so it survives
    container restarts without needing a Redis-style counter.
    """
    __tablename__ = "site_visits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    # Optional low-cardinality tag so we can slice by "page" if we ever add
    # a Docs/Blog surface. Not currently written by any code path.
    surface: Mapped[str] = mapped_column(String(32), default="app")


class AgentTrace(Base):
    """One row per agent invocation inside a pipeline generation run.

    Iteration-27 · Agent execution tracing.

    Captures *how* each agent used its resources — the prompt sent to the
    LLM, the tokens consumed, the MCP tool calls made, the skills the
    guard allowed, the input state snapshot, and the output produced.
    The thesis's Evaluation chapter uses these rows to prove that the
    multi-agent workflow is deterministic, auditable, and cost-bounded.

    `run_id` links back to `pipeline_runs.id`. It is generated up-front
    by `PipelineService.generate()` and passed through the LangGraph
    state so every agent knows which trace bucket to write into.
    """
    __tablename__ = "agent_traces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Summarised input the agent saw (keys of the shared LangGraph state).
    input_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    # Summarised output the agent produced (returned keys + shape).
    output_summary: Mapped[dict] = mapped_column(JSON, default=dict)

    # LLM usage inside this agent (aggregated across retries).
    llm_provider: Mapped[Optional[str]] = mapped_column(String(32))
    llm_model: Mapped[Optional[str]] = mapped_column(String(120))
    prompt_text: Mapped[Optional[str]] = mapped_column(Text)   # truncated at 8 KB
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)

    # Skill card (adapter names the agent was allowed to call) + actual calls.
    skills_declared: Mapped[list] = mapped_column(JSON, default=list)
    mcp_calls: Mapped[list] = mapped_column(JSON, default=list)     # [{adapter, tool, args_summary, ok, duration_ms}]

    status: Mapped[str] = mapped_column(String(16), default="ok")   # ok | error
    error: Mapped[Optional[str]] = mapped_column(Text)


class IdentityProvider(Base):
    """Iteration-26.6 · Admin-configured enterprise SSO providers.

    Complements the env-driven `OIDC_*` block in `.env` — env config still
    works for backwards compatibility, but new tenants can now add Entra ID,
    Google Workspace, or a generic OIDC provider at runtime without editing
    files or restarting the container.

    `client_secret_enc` stores a Fernet-encrypted value (see
    `services/crypto_service.py`). It is NEVER returned to the client.
    """
    __tablename__ = "identity_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uid)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # entra | google | oidc
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_secret_enc: Mapped[str] = mapped_column(Text, nullable=False)
    discovery_url: Mapped[Optional[str]] = mapped_column(String(500))
    tenant_id: Mapped[Optional[str]] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)



async def create_all() -> None:
    """Create tables if missing (lightweight alternative to Alembic for first-run bootstrap)."""
    from backend.database.connection import engine  # local import to avoid cycles
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
