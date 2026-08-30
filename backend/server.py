"""AIPP FastAPI entry point.

Kept small: all logic lives in `backend/api/*`, `backend/services/*`, and
`backend/orchestrator/*`. This file just wires everything together and boots
the database schema on startup.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# supervisor runs uvicorn from /app/backend; make `backend.*` importable
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from backend.api import agent_traces, auth, deployment, identity_providers, integrations, llm, pipeline_doctor, pipelines, policy, proxy, repositories, research, site, slack, webhooks, workflows
from backend.core.config import get_settings
from backend.core.logging import get_logger, setup_logging
from backend.database.models import create_all
from backend.mcp.client import get_mcp_client
from backend.services.auth_service import seed_default_admin

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AIPP starting up — creating DB schema if missing")
    try:
        await create_all()
    except Exception as e:
        logger.error("DB schema init failed: %s", e)
    try:
        await seed_default_admin()
    except Exception as e:
        logger.error("auth: default admin seed failed: %s", e)
    logger.info("MCP adapters configured: %s", get_mcp_client().configured_adapters())
    yield
    logger.info("AIPP shutting down")


app = FastAPI(
    title="AIPP — Automated Pipeline Platform",
    version="0.1.0",
    lifespan=lifespan,
    description="Backend for the AIPP MS research project.",
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/")
async def root() -> dict:
    return {
        "service": "AIPP",
        "version": "0.1.0",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "configured_mcp_adapters": get_mcp_client().configured_adapters(),
    }


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/mcp/tools")
async def mcp_tools() -> dict:
    return get_mcp_client().list_tools()


@app.get("/api/agents")
async def list_agents_endpoint() -> dict:
    """Public agent-catalog endpoint.

    Returns every agent registered in `backend/agents/registry.py` as a
    structured card. Used by:
      - the UI to render an "About the agents" panel;
      - the docs to auto-generate the agent matrix;
      - other AI systems that want to discover what AIPP can do.

    The response is stable and machine-readable — treat it as a public
    contract.
    """
    from backend.agents.registry import list_agents
    agents = list_agents()
    return {
        "total": len(agents),
        "agents": [s.to_card() for s in agents],
    }


app.include_router(repositories.router)
app.include_router(pipelines.router)
app.include_router(pipeline_doctor.router)
app.include_router(workflows.router)
app.include_router(research.router)
app.include_router(deployment.router)
app.include_router(llm.router)
app.include_router(auth.router)
app.include_router(policy.router)
app.include_router(integrations.router)
app.include_router(site.router)
app.include_router(identity_providers.router)
app.include_router(agent_traces.router)
app.include_router(proxy.router)
app.include_router(webhooks.router)
app.include_router(slack.router)
