"""Tests for the RCA auto-embedding + retrieval loop.

Covers:
  1. `_build_content()` composes a compact, retrieval-friendly string
     from a real RCAReport dict.
  2. `embed_and_persist()` swallows every failure path — pgvector
     missing, DB offline, embedder crash — and returns False cleanly.
  3. `find_similar()` returns an empty list (not raises) when pgvector
     is unavailable.
  4. `format_context_block()` produces the exact string the LLM prompt
     expects, or empty when nothing was retrieved.
  5. `GET /api/pipeline-doctor/similar` validates its query params and
     bubbles the service result 1:1.
  6. `POST /api/pipeline-doctor/analyze` calls the retrieval hook and
     the embed hook — mocked out end-to-end so we test the wiring
     without needing a live Postgres.
"""
from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.services import rca_embedding_service


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
class TestBuildContent:
    def test_composes_root_cause_first(self):
        content = rca_embedding_service._build_content({
            "root_cause": "Pod OOMKilled — memory limit too low",
            "failed_stage": "test",
            "ci_platform": "github-actions",
            "corrective_actions": ["Bump memory to 512Mi"],
            "preventive_actions": ["Add memory-request policy"],
        })
        # Root cause on the first line for max cosine signal.
        assert content.splitlines()[0].startswith("Root cause: Pod OOMKilled")
        assert "Failed stage: test" in content
        assert "Bump memory to 512Mi" in content
        assert "Add memory-request policy" in content

    def test_handles_empty_report(self):
        content = rca_embedding_service._build_content({})
        assert content == "(empty rca)"

    def test_never_leaks_evidence_lines(self):
        """Evidence snippets often carry project-specific paths — leaving
        them out keeps retrieval generic."""
        content = rca_embedding_service._build_content({
            "root_cause": "Timeout",
            "evidence": [{"snippet": "SECRET_LOG_LINE_WITH_PATH=/srv/foo"}],
        })
        assert "SECRET_LOG_LINE_WITH_PATH" not in content


class TestFormatContextBlock:
    def test_empty_input_gives_empty_output(self):
        assert rca_embedding_service.format_context_block([]) == ""

    def test_lists_every_hit_with_similarity(self):
        block = rca_embedding_service.format_context_block([
            {"ci_platform": "gha", "similarity": 0.87,
             "root_cause": "OOM"},
            {"ci_platform": "ado", "similarity": 0.62,
             "root_cause": "flaky test"},
        ])
        assert "similarity 0.87" in block
        assert "OOM" in block
        assert "flaky test" in block
        # Must instruct the LLM NOT to cite these as current-log evidence.
        assert "do NOT cite" in block


# ---------------------------------------------------------------------------
# embed_and_persist  — degrades gracefully in every failure mode
# ---------------------------------------------------------------------------
class TestEmbedAndPersist:
    @pytest.mark.asyncio
    async def test_swallows_pgvector_missing(self):
        """If the rca_embeddings table is absent, we log and return False —
        never propagate the error to the RCA save."""
        fake_svc = AsyncMock()
        fake_svc.embed = AsyncMock(return_value=[0.1] * 1536)

        class _BrokenSess:
            async def execute(self, *a, **kw):
                raise RuntimeError('relation "rca_embeddings" does not exist')

            async def commit(self):
                pass

        class _BrokenCtx:
            async def __aenter__(self):
                return _BrokenSess()

            async def __aexit__(self, *a):
                return False

        with patch("backend.services.rca_embedding_service.session_scope",
                   return_value=_BrokenCtx()):
            ok = await rca_embedding_service.embed_and_persist(
                "fake-uuid", {"root_cause": "x"}, svc=fake_svc,
            )
        assert ok is False

    @pytest.mark.asyncio
    async def test_swallows_embedder_crash(self):
        fake_svc = AsyncMock()
        fake_svc.embed = AsyncMock(side_effect=RuntimeError("openai down"))
        ok = await rca_embedding_service.embed_and_persist(
            "fake-uuid", {"root_cause": "x"}, svc=fake_svc,
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_happy_path_inserts_row(self):
        fake_svc = AsyncMock()
        fake_svc.embed = AsyncMock(return_value=[0.5] * 1536)

        insert_calls: list[dict] = []

        class _Sess:
            async def execute(self, stmt, params):
                insert_calls.append({"stmt": str(stmt), "params": params})

            async def commit(self):
                pass

        class _Ctx:
            async def __aenter__(self):
                return _Sess()

            async def __aexit__(self, *a):
                return False

        with patch("backend.services.rca_embedding_service.session_scope",
                   return_value=_Ctx()):
            ok = await rca_embedding_service.embed_and_persist(
                "abc-123", {"root_cause": "OOM"}, svc=fake_svc,
            )
        assert ok is True
        assert len(insert_calls) == 1
        c = insert_calls[0]
        assert "INSERT INTO rca_embeddings" in c["stmt"]
        assert c["params"]["rid"] == "abc-123"
        # Vec literal is bracketed pgvector-friendly.
        assert c["params"]["vec"].startswith("[") and c["params"]["vec"].endswith("]")
        assert "Root cause: OOM" in c["params"]["ct"]


# ---------------------------------------------------------------------------
# find_similar  — safe fallbacks
# ---------------------------------------------------------------------------
class TestFindSimilar:
    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        assert await rca_embedding_service.find_similar("   ") == []

    @pytest.mark.asyncio
    async def test_pgvector_missing_returns_empty(self):
        fake_svc = AsyncMock()
        fake_svc.embed = AsyncMock(return_value=[0.1] * 1536)

        class _BrokenSess:
            async def execute(self, *a, **kw):
                raise RuntimeError('type "vector" does not exist')

        class _BrokenCtx:
            async def __aenter__(self):
                return _BrokenSess()

            async def __aexit__(self, *a):
                return False

        with patch("backend.services.rca_embedding_service.session_scope",
                   return_value=_BrokenCtx()):
            hits = await rca_embedding_service.find_similar("x", svc=fake_svc)
        assert hits == []

    @pytest.mark.asyncio
    async def test_returns_shaped_rows(self):
        fake_svc = AsyncMock()
        fake_svc.embed = AsyncMock(return_value=[0.5] * 1536)

        fake_rows = [
            {
                "rca_id": "r-1",
                "content": "Root cause: OOM\n" * 40,
                "ci_platform": "gha",
                "confidence": 0.9,
                "report_json": {"root_cause": "OOM",
                                "failed_stage": "test"},
                "created_at": datetime.now(timezone.utc),
                "similarity": 0.87,
            },
        ]

        class _Result:
            def mappings(self):
                class _M:
                    @staticmethod
                    def all():
                        return fake_rows
                return _M()

        class _Sess:
            async def execute(self, *a, **kw):
                return _Result()

        class _Ctx:
            async def __aenter__(self):
                return _Sess()

            async def __aexit__(self, *a):
                return False

        with patch("backend.services.rca_embedding_service.session_scope",
                   return_value=_Ctx()):
            hits = await rca_embedding_service.find_similar(
                "pod oomkilled", limit=5, svc=fake_svc,
            )
        assert len(hits) == 1
        h = hits[0]
        assert h["rca_id"] == "r-1"
        assert h["similarity"] == 0.87
        assert h["root_cause"] == "OOM"
        assert h["ci_platform"] == "gha"
        # Content preview capped so we don't dump the entire log back.
        assert len(h["content_preview"]) <= 400


# ---------------------------------------------------------------------------
# /api/pipeline-doctor/similar endpoint
# ---------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "unused-for-doctor-tests")
    get_settings.cache_clear()
    from backend.server import app
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


class TestSimilarEndpoint:
    def test_missing_query_returns_400(self, client):
        r = client.get("/api/pipeline-doctor/similar?q=")
        assert r.status_code == 400

    def test_out_of_range_limit_returns_400(self, client):
        r = client.get("/api/pipeline-doctor/similar?q=oom&limit=99")
        assert r.status_code == 400

    def test_happy_path_bubbles_service_output(self, client):
        expected = [
            {"rca_id": "r-1", "similarity": 0.9, "root_cause": "OOM",
             "ci_platform": "gha", "failed_stage": "test",
             "confidence": 0.8, "created_at": "2026-02-18T10:00:00+00:00",
             "content_preview": "Root cause: OOM"},
        ]
        with patch("backend.api.pipeline_doctor.rca_embedding_service.find_similar",
                   new_callable=AsyncMock) as mock_find:
            mock_find.return_value = expected
            r = client.get("/api/pipeline-doctor/similar?q=pod%20oom&limit=3")
        assert r.status_code == 200
        body = r.json()
        assert body["query"] == "pod oom"
        assert body["hits"] == 1
        assert body["results"] == expected
        mock_find.assert_awaited_once()
        args, kwargs = mock_find.await_args
        assert args[0] == "pod oom"
        assert kwargs.get("limit") == 3


# ---------------------------------------------------------------------------
# /api/pipeline-doctor/analyze  — retrieval + embed wiring end-to-end
# ---------------------------------------------------------------------------
class TestAnalyzeWiring:
    def test_analyze_calls_retrieval_and_embed_hooks(self, client, tmp_path):
        """The RAG loop:
             1. find_similar() is called with the log-derived query
             2. run_rca() receives the context block prepended
             3. embed_and_persist() fires after the RCAReport is saved
             4. `retrieved_from_memory` shows up in the response
        """
        fake_similar = [
            {"rca_id": "r-past-1", "similarity": 0.82,
             "root_cause": "Pod OOMKilled",
             "ci_platform": "gha", "failed_stage": "test",
             "confidence": 0.8, "created_at": "2026-02-01T00:00:00+00:00",
             "content_preview": "Root cause: Pod OOMKilled"},
        ]
        fake_rca = {
            "ci_platform": "github-actions",
            "failed_stage": "test",
            "root_cause": "OOMKill on runner",
            "confidence": 0.7,
            "evidence": [], "ai_inferences": [],
            "corrective_actions": ["increase memory"],
            "preventive_actions": [],
        }

        with patch("backend.api.pipeline_doctor.rca_embedding_service.find_similar",
                   new_callable=AsyncMock) as mock_find, \
             patch("backend.api.pipeline_doctor.rca_embedding_service.embed_and_persist",
                   new_callable=AsyncMock) as mock_embed, \
             patch("backend.api.pipeline_doctor.run_rca",
                   new_callable=AsyncMock) as mock_run, \
             patch("backend.api.pipeline_doctor.session_scope") as mock_ss:
            mock_find.return_value = fake_similar
            mock_run.return_value = fake_rca
            mock_embed.return_value = True

            # Emulate the SQLAlchemy session context manager so the row's
            # `.id` is populated after `.flush()`.
            class _Sess:
                def __init__(self):
                    self._row = None

                def add(self, obj):
                    obj.id = "generated-uuid"
                    self._row = obj

                async def flush(self):
                    pass

            class _Ctx:
                async def __aenter__(self_inner):
                    return _Sess()

                async def __aexit__(self_inner, *a):
                    return False

            mock_ss.return_value = _Ctx()

            r = client.post(
                "/api/pipeline-doctor/analyze",
                data={
                    "ci_platform": "github-actions",
                    "incident_context": "smoke test failed on main",
                    "raw_log": "L1: build ok\nL2: pod OOMKilled\n" * 40,
                },
            )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == "generated-uuid"
        # `retrieved_from_memory` surfaces retrieval provenance.
        assert body["retrieved_from_memory"] == [{
            "rca_id": "r-past-1", "similarity": 0.82,
            "root_cause": "Pod OOMKilled",
        }]

        # The retrieval query includes both the operator context AND some
        # log lines, capped at 4000 chars.
        rq = mock_find.await_args.args[0]
        assert "smoke test failed" in rq
        assert len(rq) <= 4000

        # run_rca received the augmented context (past incidents + user context).
        aug = mock_run.await_args.kwargs["incident_context"]
        assert "Pod OOMKilled" in aug
        assert "smoke test failed on main" in aug

        # embed_and_persist fired with the persisted RCA id + report.
        mock_embed.assert_awaited_once()
        args = mock_embed.await_args.args
        assert args[0] == "generated-uuid"
        assert args[1]["root_cause"] == "OOMKill on runner"

    def test_analyze_still_works_when_retrieval_returns_empty(self, client):
        """No past RCAs yet → no `retrieved_from_memory` key, no context
        block prepended. The RCA response is otherwise identical."""
        with patch("backend.api.pipeline_doctor.rca_embedding_service.find_similar",
                   new_callable=AsyncMock, return_value=[]), \
             patch("backend.api.pipeline_doctor.rca_embedding_service.embed_and_persist",
                   new_callable=AsyncMock, return_value=False), \
             patch("backend.api.pipeline_doctor.run_rca",
                   new_callable=AsyncMock) as mock_run, \
             patch("backend.api.pipeline_doctor.session_scope") as mock_ss:
            mock_run.return_value = {
                "ci_platform": "gha", "root_cause": "flaky",
                "confidence": 0.4, "evidence": [], "ai_inferences": [],
                "corrective_actions": [], "preventive_actions": [],
            }

            class _Sess:
                def add(self, obj):
                    obj.id = "uuid-2"

                async def flush(self):
                    pass

            class _Ctx:
                async def __aenter__(self_inner):
                    return _Sess()

                async def __aexit__(self_inner, *a):
                    return False

            mock_ss.return_value = _Ctx()

            r = client.post(
                "/api/pipeline-doctor/analyze",
                data={
                    "ci_platform": "gha",
                    "incident_context": "",
                    "raw_log": "L1: build ok\nL2: intermittent failure\n" * 5,
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "uuid-2"
        assert "retrieved_from_memory" not in body
        # No context block because no similar RCAs were retrieved.
        aug = mock_run.await_args.kwargs["incident_context"]
        assert aug in (None, "")
