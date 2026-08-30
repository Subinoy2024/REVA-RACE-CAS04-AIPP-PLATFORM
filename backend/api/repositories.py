"""Repository probe endpoint (used by the Gradio 'Test Connection' button)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.core.exceptions import RepositoryAccessError
from backend.models.repository import RepositoryRequest
from backend.services.repository_service import RepositoryService

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.post("/probe")
async def probe_repository(req: RepositoryRequest) -> dict:
    try:
        meta = await RepositoryService().probe(req)
    except RepositoryAccessError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True, "repository": meta}
