"""Integrations API — user-onboarded deployment platforms + auto-deploy.

All endpoints are scoped by the authenticated user (owner_email). The
underlying credentials are encrypted at rest — see
`services/crypto_service.py`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.exceptions import RepositoryAccessError
from backend.core.logging import get_logger
from backend.services import deployment_targets as svc
from backend.services.auth_service import get_current_user

router = APIRouter(prefix="/api/integrations", tags=["integrations"])
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class TargetCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120,
                      description="Nickname to identify this integration in the UI.")
    platform: str = Field(..., description="`github_actions` | `azure_devops` | `gitlab_ci`")
    repo_url: str = Field(
        "",
        description=(
            "Optional saved default deployment repository URL. Leave blank "
            "to pick the deployment repo at push time on the Pipeline "
            "Generator page (iteration-26.7)."
        ),
    )
    default_branch: str = Field("main", min_length=1)
    token: str = Field(..., min_length=8, max_length=400,
                       description="Write-scoped PAT. Stored Fernet-encrypted.")
    extra: dict = Field(default_factory=dict,
                        description="Platform-specific extras (unused for v1).")


class DeployRequest(BaseModel):
    target_id: str = Field(..., description="UUID of an onboarded deployment target.")
    ci_platform: str = Field(..., description="github_actions | azure_devops | gitlab_ci | harness | tekton")
    yaml_content: str = Field(..., min_length=20)
    mode: str = Field("pr", description="`pr` (safest, recommended) | `commit`")
    branch: str | None = Field(None, description="Overrides target's default_branch.")
    repo_url: str | None = Field(
        None,
        description=(
            "Overrides the target's saved repo_url. REQUIRED at push time if "
            "the target has no saved repo_url (iteration-26.7)."
        ),
    )
    commit_message: str | None = None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("/targets")
async def list_targets(current: dict = Depends(get_current_user)) -> dict:
    """Return all deployment targets belonging to the authenticated user."""
    items = await svc.list_targets(owner_email=current["email"])
    return {"total": len(items), "targets": items}


@router.post("/targets")
async def create_target(body: TargetCreate,
                        current: dict = Depends(get_current_user)) -> dict:
    try:
        return await svc.create_target(
            owner_email=current["email"],
            name=body.name,
            platform=body.platform,
            repo_url=body.repo_url,
            default_branch=body.default_branch,
            token_plain=body.token,
            extra=body.extra,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/targets/{target_id}")
async def delete_target(target_id: str,
                        current: dict = Depends(get_current_user)) -> dict:
    try:
        tid = UUID(target_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target id")
    ok = await svc.delete_target(owner_email=current["email"], target_id=tid)
    if not ok:
        raise HTTPException(status_code=404, detail="Target not found")
    return {"ok": True}


@router.post("/targets/{target_id}/test")
async def test_target(target_id: str,
                      current: dict = Depends(get_current_user)) -> dict:
    try:
        tid = UUID(target_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target id")
    try:
        return await svc.test_target(owner_email=current["email"], target_id=tid)
    except RepositoryAccessError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Auto-deploy
# ---------------------------------------------------------------------------
@router.post("/deploy")
async def deploy(body: DeployRequest,
                 current: dict = Depends(get_current_user)) -> dict:
    """Auto-push generated YAML to the onboarded deployment target."""
    try:
        tid = UUID(body.target_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target id")
    try:
        return await svc.deploy(
            owner_email=current["email"],
            target_id=tid,
            ci_platform=body.ci_platform,
            yaml_content=body.yaml_content,
            mode=body.mode,
            branch=body.branch,
            repo_url_override=body.repo_url,
            commit_message=body.commit_message,
        )
    except RepositoryAccessError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("integrations.deploy failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments")
async def list_deployments(current: dict = Depends(get_current_user)) -> dict:
    items = await svc.list_deployments(current["email"], limit=100)
    return {"total": len(items), "deployments": items}
