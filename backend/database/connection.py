"""SQLAlchemy async engine + session factory. All modules acquire a session from here."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.postgres_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session with commit/rollback semantics."""
    async with AsyncSessionLocal() as sess:
        try:
            yield sess
            await sess.commit()
        except Exception:
            await sess.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with AsyncSessionLocal() as sess:
        yield sess
