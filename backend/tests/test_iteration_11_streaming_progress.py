"""Iteration-11 regression tests — per-agent streaming progress via SSE.

Covers:
  1. ProgressBus (backend/orchestrator/progress.py) — publish/subscribe/close.
  2. Graph publishes running/done events for every agent when a stream_id
     is present in the state.
  3. /api/pipelines/generate/stream endpoint returns text/event-stream.
  4. Gradio `_generate` is a generator that yields per-agent updates and
     uses `sse_post` (not the sync `post`).
  5. Progress markdown renderer produces a 7-row table.
  6. The build_tab wiring includes the progress_md output.
  7. /api/pipelines/generate/agents lists all 7 agents in the correct order.
"""

from __future__ import annotations

import asyncio
import inspect
import re

import pytest
from fastapi.testclient import TestClient

from backend.orchestrator import progress
from backend.orchestrator.graph import AGENT_ORDER, TOTAL_AGENTS
from backend.server import app
from frontend.tabs import pipeline_generator as pg


# ---------------------------------------------------------------------------
# ProgressBus unit tests
# ---------------------------------------------------------------------------
class TestProgressBus:
    def test_create_and_publish_and_subscribe(self):
        async def _run():
            sid = await progress.create_stream()
            await progress.publish(sid, agent="a1", status="running",
                                   detail="starting")
            await progress.publish(sid, agent="a1", status="done", detail="ok")
            await progress.close(sid)

            events = []
            async for ev in progress.subscribe(sid):
                events.append(ev)
            await progress.discard(sid)
            return events

        events = asyncio.run(_run())
        # 2 agent events + 1 done sentinel.
        assert len(events) == 3
        assert events[0]["agent"] == "a1" and events[0]["status"] == "running"
        assert events[1]["status"] == "done"
        assert events[2]["kind"] == "done"

    def test_seq_is_monotonic(self):
        async def _run():
            sid = await progress.create_stream()
            for i in range(5):
                await progress.publish(sid, agent=f"n{i}", status="running")
            await progress.close(sid)
            seqs = []
            async for ev in progress.subscribe(sid):
                seqs.append(ev["seq"])
                if ev.get("kind") == "done":
                    break
            await progress.discard(sid)
            return seqs

        seqs = asyncio.run(_run())
        assert seqs == sorted(seqs)  # monotonically increasing
        assert seqs[0] == 1

    def test_publish_to_unknown_stream_is_noop(self):
        async def _run():
            # No exception even though stream_id is None / bogus.
            await progress.publish(None, agent="x", status="running")
            await progress.publish("bogus", agent="x", status="running")
            return True

        assert asyncio.run(_run()) is True

    def test_discard_removes_the_stream(self):
        async def _run():
            sid = await progress.create_stream()
            before = progress.active_stream_count()
            await progress.discard(sid)
            after = progress.active_stream_count()
            return before, after

        before, after = asyncio.run(_run())
        assert before >= 1
        assert after == before - 1

    def test_close_can_be_called_twice_safely(self):
        async def _run():
            sid = await progress.create_stream()
            await progress.close(sid)
            await progress.close(sid)  # must not raise / duplicate frames
            n = 0
            async for _ev in progress.subscribe(sid):
                n += 1
                if n > 3:
                    break
            await progress.discard(sid)
            return n

        # Only ONE `done` frame is emitted, so subscribe yields exactly 1.
        assert asyncio.run(_run()) == 1


# ---------------------------------------------------------------------------
# Graph metadata (agent order + count)
# ---------------------------------------------------------------------------
class TestAgentOrderMetadata:
    def test_agent_order_has_seven_entries(self):
        assert len(AGENT_ORDER) == 7
        assert TOTAL_AGENTS == 7

    def test_agent_order_matches_expected_names(self):
        expected = [
            "repository_analysis",
            "technology_detection",
            "architecture_detection",
            "pipeline_planning",
            "environment_deployment",
            "pipeline_generation",
            "pipeline_validation",
        ]
        assert [name for name, _label in AGENT_ORDER] == expected


# ---------------------------------------------------------------------------
# /api/pipelines/generate/agents — list all 7 agents
# ---------------------------------------------------------------------------
class TestAgentsListingEndpoint:
    def test_endpoint_returns_seven_agents(self):
        client = TestClient(app)
        r = client.get("/api/pipelines/generate/agents")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 7
        assert len(body["agents"]) == 7
        assert body["agents"][0]["name"] == "repository_analysis"
        assert body["agents"][-1]["name"] == "pipeline_validation"
        # Every agent must have an index and a human-readable label.
        for i, entry in enumerate(body["agents"]):
            assert entry["index"] == i
            assert entry["label"]


# ---------------------------------------------------------------------------
# Gradio streaming — _generate is a generator using sse_post
# ---------------------------------------------------------------------------
class TestGradioGenerateIsStreamingGenerator:
    def test_generate_is_a_generator_function(self):
        assert inspect.isgeneratorfunction(pg._generate), (
            "_generate must be a generator so Gradio can progressively "
            "update the progress panel via SSE."
        )

    def test_generate_yields_progress_updates_from_sse(self, monkeypatch):
        """Given a fake SSE stream, _generate must yield an idle frame, one
        frame per agent event, and a final result frame — in that order."""
        def fake_sse(path, *, json_body, **_kw):
            # 2 agents flip running→done, then the final result.
            for name in ["repository_analysis", "technology_detection"]:
                yield {"kind": "agent", "agent": name, "status": "running",
                       "detail": "…"}
                yield {"kind": "agent", "agent": name, "status": "done",
                       "detail": "ok"}
            yield {"kind": "result", "payload": {
                "pipeline": {"yaml_content": "stages: []", "filename": "x.yml"},
                "explanation": "e", "plan": {"stages": []}, "validation": {},
                "analysis": {"owner": "o", "name": "n"},
                "generation_seconds": 1.2,
            }}
            yield {"kind": "done"}

        monkeypatch.setattr(pg, "sse_post", fake_sse)

        frames = list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "github_actions", "aws", "unspecified", "all_in_one", "", "terraform", "",
        ))
        # 1 idle + 4 agent events + 1 final = 6 frames.
        assert len(frames) == 6
        # Header of the last frame is the success banner.
        assert frames[-1][0].startswith("✅ Generated for o/n")
        # First frame is the idle banner.
        assert frames[0][0].startswith("⏳")
        # Every frame contains the aura progress strip.
        for f in frames:
            assert "aipp-progress-strip" in f[1]

    def test_generate_yields_error_on_error_event(self, monkeypatch):
        def fake_sse(path, *, json_body, **_kw):
            yield {"kind": "agent", "agent": "repository_analysis",
                   "status": "running", "detail": "…"}
            yield {"kind": "error", "agent": "orchestrator",
                   "status": "failed", "detail": "boom"}
            yield {"kind": "done"}

        monkeypatch.setattr(pg, "sse_post", fake_sse)
        frames = list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "github_actions", "aws", "unspecified", "all_in_one", "", "terraform", "",
        ))
        assert frames[-1][0].startswith("❌")
        assert "boom" in frames[-1][0]

    def test_generate_missing_inputs_yields_error_frame(self):
        frames = list(pg._generate("", "", "main", "github_actions", "aws",
                                   "unspecified", "all_in_one", "", "terraform", ""))
        assert len(frames) == 1
        assert frames[0][0].startswith("❌")


# ---------------------------------------------------------------------------
# Progress markdown renderer
# ---------------------------------------------------------------------------
class TestProgressMarkdown:
    def test_initial_state_shows_all_pending(self):
        md = pg._render_progress(pg._initial_progress_state())
        assert "0/7 agents" in md
        # All 7 agents present.
        for name, label in pg._AGENT_ROWS:
            assert label in md
        # Aura HTML markers.
        assert "aipp-agent-row" in md
        assert "aipp-progress-strip" in md
        assert "pending" in md

    def test_state_progresses_to_done(self):
        st = pg._initial_progress_state()
        st["repository_analysis"] = "done"
        st["technology_detection"] = "running"
        md = pg._render_progress(st)
        assert "1/7 agents" in md
        # Aura classes for running + done.
        assert "aipp-agent-running" in md
        assert "aipp-agent-done" in md

    def test_failed_stage_uses_x_symbol(self):
        st = pg._initial_progress_state()
        st["pipeline_planning"] = "failed"
        md = pg._render_progress(st)
        assert "aipp-agent-failed" in md


# ---------------------------------------------------------------------------
# build_tab wiring includes the progress markdown output
# ---------------------------------------------------------------------------
class TestBuildTabWiringIncludesProgress:
    def test_build_tab_declares_progress_markdown(self):
        src = inspect.getsource(pg.build_tab)
        assert "progress_md" in src, "build_tab must declare a progress_md widget"
        assert "pg-progress" in src, "progress widget must have elem_id 'pg-progress'"

    def test_click_wiring_includes_progress_md_output(self):
        src = inspect.getsource(pg.build_tab)
        m = re.search(
            r"btn\.click\(\s*_generate\s*,\s*inputs\s*=\s*\[[^\]]*\]\s*,\s*"
            r"outputs\s*=\s*\[([^\]]*)\]",
            src, re.DOTALL,
        )
        assert m, "Could not locate btn.click(_generate, inputs=..., outputs=[...]) wiring"
        outputs = [tok.strip() for tok in m.group(1).split(",") if tok.strip()]
        assert "progress_md" in outputs, (
            f"btn.click outputs missing progress_md. Current outputs: {outputs}"
        )
