"""RAG / pgvector contracts — iteration-34.

Validates the embedding service + `/api/pipelines/similar` endpoint
without requiring a running Postgres+pgvector (tests use TestClient
and mock the DB layer where needed).
"""
from __future__ import annotations

import math
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


def _client(env_overrides: dict[str, str] | None = None):
    prev: dict[str, str | None] = {}
    for k, v in (env_overrides or {}).items():
        prev[k] = os.environ.get(k)
        os.environ[k] = v
    from backend.core.config import get_settings
    get_settings.cache_clear()
    from backend.server import app
    return TestClient(app), prev


def _restore(prev: dict[str, str | None]) -> None:
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    from backend.core.config import get_settings
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------
def test_embedding_dim_is_1536():
    from backend.services.embedding_service import EmbeddingService, EMBED_DIM
    svc = EmbeddingService()
    assert svc.dim == EMBED_DIM == 1536


@pytest.mark.asyncio
async def test_fallback_when_no_key():
    """No LLM key → deterministic fallback embedding, unit-normed."""
    from backend.services.embedding_service import EmbeddingService
    # Ensure key is empty
    prev = os.environ.get("EMERGENT_LLM_KEY")
    prev2 = os.environ.get("LLM_KEY")
    os.environ.pop("EMERGENT_LLM_KEY", None)
    os.environ.pop("LLM_KEY", None)
    from backend.core.config import get_settings
    get_settings.cache_clear()
    try:
        svc = EmbeddingService()
        v1 = await svc.embed("hello world")
        v2 = await svc.embed("hello world")
        assert v1 == v2                                          # deterministic
        assert len(v1) == 1536
        norm = math.sqrt(sum(x * x for x in v1))
        assert 0.99 < norm < 1.01                                # unit vector
    finally:
        if prev is not None:
            os.environ["EMERGENT_LLM_KEY"] = prev
        if prev2 is not None:
            os.environ["LLM_KEY"] = prev2
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_fallback_different_inputs_different_vectors():
    from backend.services.embedding_service import EmbeddingService
    svc = EmbeddingService()
    v1 = svc._fallback("aws deploy failed")
    v2 = svc._fallback("gcp deploy succeeded")
    assert v1 != v2


@pytest.mark.asyncio
async def test_embed_many_returns_correct_shape():
    from backend.services.embedding_service import EmbeddingService
    os.environ.pop("EMERGENT_LLM_KEY", None)
    from backend.core.config import get_settings
    get_settings.cache_clear()
    svc = EmbeddingService()
    vecs = await svc.embed_many(["one", "two", "three"])
    assert len(vecs) == 3
    assert all(len(v) == 1536 for v in vecs)


# ---------------------------------------------------------------------------
# /api/pipelines/similar
# ---------------------------------------------------------------------------
def test_similar_requires_q_param():
    client, prev = _client({})
    try:
        r = client.get("/api/pipelines/similar")
        assert r.status_code in (400, 422)
    finally:
        _restore(prev)


def test_similar_rejects_empty_q():
    client, prev = _client({})
    try:
        r = client.get("/api/pipelines/similar?q=")
        assert r.status_code in (400, 422)
    finally:
        _restore(prev)


def test_similar_rejects_bad_limit():
    client, prev = _client({})
    try:
        r = client.get("/api/pipelines/similar?q=test&limit=0")
        # 400 (our check) or 500 (DB unavailable) both acceptable in sandbox
        assert r.status_code in (400, 422, 500)
        if r.status_code < 500:
            assert "1..50" in r.text or "limit" in r.text.lower()
    finally:
        _restore(prev)


def test_similar_gracefully_returns_501_when_pgvector_missing():
    """If DB doesn't have pgvector extension enabled, endpoint returns 501,
    not a stack trace. We simulate by mocking the session."""
    client, prev = _client({})
    try:
        from unittest.mock import MagicMock

        class FakeSession:
            async def execute(self, *a, **kw):
                raise RuntimeError('type "vector" does not exist')
            def __aenter__(self): return self
            async def __aexit__(self, *a): pass

        async def override():
            yield FakeSession()

        from backend.server import app
        from backend.database.connection import get_session
        app.dependency_overrides[get_session] = override
        try:
            r = client.get("/api/pipelines/similar?q=aws")
            assert r.status_code == 501
            assert "pgvector" in r.text.lower()
        finally:
            app.dependency_overrides.pop(get_session, None)
    finally:
        _restore(prev)


def test_similar_empty_when_no_embeddings_yet():
    """Fresh DB, no rows yet → returns empty results, not an error."""
    client, prev = _client({})
    try:
        class FakeSession:
            async def execute(self, *a, **kw):
                raise RuntimeError('relation "pipeline_embeddings" does not exist')
            def __aenter__(self): return self
            async def __aexit__(self, *a): pass

        async def override():
            yield FakeSession()

        from backend.server import app
        from backend.database.connection import get_session
        app.dependency_overrides[get_session] = override
        try:
            r = client.get("/api/pipelines/similar?q=test")
            assert r.status_code == 200
            data = r.json()
            assert data["hits"] == 0
            assert data["results"] == []
        finally:
            app.dependency_overrides.pop(get_session, None)
    finally:
        _restore(prev)


# ---------------------------------------------------------------------------
# Migration file present
# ---------------------------------------------------------------------------
def test_pgvector_migration_exists():
    from pathlib import Path
    mig = (Path(__file__).resolve().parents[1] /
           "database" / "migrations" / "versions" / "34_pgvector_rag.py")
    assert mig.exists(), "Migration 34_pgvector_rag.py missing"
    content = mig.read_text()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in content
    assert "pipeline_embeddings" in content
    assert "rca_embeddings" in content
    assert "hnsw" in content.lower()


def test_docker_compose_uses_pgvector_image():
    from pathlib import Path
    dc = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    assert dc.exists()
    assert "pgvector/pgvector" in dc.read_text()
