"""Audit-log service — every agent decision + tool call is recorded here."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import session_scope
from backend.database.models import AuditLog


class AuditService:
    async def log(
        self,
        *,
        action: str,
        actor: Optional[str] = None,
        tool: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with session_scope() as sess:
            sess.add(AuditLog(action=action, actor=actor, tool=tool, details_json=details or {}))

    async def recent(self, session: AsyncSession, limit: int = 50) -> list[dict]:
        rows = (await session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))).scalars().all()
        return [
            {
                "id": str(r.id), "action": r.action, "actor": r.actor,
                "tool": r.tool, "details": r.details_json,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
