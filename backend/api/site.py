"""Site visit counter — powers the footer number.

Iteration-26.5.

Two endpoints — both **unauthenticated** because the counter fires on the
login page before the user has signed in.

  POST /api/site/visit     — record a landing; returns the new total.
  GET  /api/site/visits    — read-only total (used by the footer refresh).

Design notes:
  * Never returns PII. Never stores IP or cookies.
  * Uses a single SQL COUNT — fine for our expected traffic. If this ever
    grows past ~1M rows, swap for a materialized counter row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import get_session, session_scope
from backend.database.models import SiteVisit


router = APIRouter(prefix="/api/site", tags=["site"])


class VisitCount(BaseModel):
    count: int


@router.post("/visit", response_model=VisitCount)
async def record_visit() -> VisitCount:
    """Insert one visit row and return the updated total."""
    async with session_scope() as sess:
        sess.add(SiteVisit(surface="app"))
        await sess.flush()
    async with session_scope() as sess:
        total = await sess.scalar(select(func.count(SiteVisit.id)))
    return VisitCount(count=int(total or 0))


@router.get("/visits", response_model=VisitCount)
async def read_visits(sess: AsyncSession = Depends(get_session)) -> VisitCount:
    total = await sess.scalar(select(func.count(SiteVisit.id)))
    return VisitCount(count=int(total or 0))
