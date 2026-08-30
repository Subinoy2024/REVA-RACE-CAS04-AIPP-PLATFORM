"""Iteration-20 (P2 batch) — n8n write actions + LLM token streaming.

Covers:
  * n8n MCP adapter registers execute/activate/deactivate/ping tools.
  * `/api/workflows/n8n/{ping,execute,activate,deactivate}` endpoints exist,
    return proper 400/502 wrapping when n8n is not configured / fails, and
    audit every write.
  * Frontend `n8n_status` tab exposes Test connection + Execute + Activate
    + Deactivate buttons wired to the new endpoints.
  * `progress.bind_stream_id` publishes a context-local stream_id that
    `progress.current_stream_id()` reads back inside async code.
  * `BaseAgent._invoke_llm` uses `stream_message` only when a stream_id
    is bound, and falls back to `send_message` otherwise.
  * Frontend `_render_progress()` accepts an optional `llm_stream` arg and
    appends a "Live LLM output" section.
  * Frontend `_generate()` consumes `kind="token"` events, accumulates a
    buffer, and re-renders the progress panel with the live tail.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock

import pytest

from backend.mcp.adapters.n8n import N8nAdapter
from backend.orchestrator import progress
from frontend.tabs import n8n_status as n8n_tab
from frontend.tabs import pipeline_generator as pg


# --------------------------------------------------------------------------- #
# 1. n8n MCP adapter surface
# --------------------------------------------------------------------------- #
class TestN8nAdapterRegistersWriteTools:
    def test_all_four_tools_are_registered(self):
        adapter = N8nAdapter()
        registered = list(adapter._tools.keys())
        for tool in ("list_workflows", "get_executions",
                     "execute_workflow", "activate_workflow",
                     "deactivate_workflow", "ping"):
            assert tool in registered, f"missing tool: {tool}"

    def test_execute_workflow_signature_requires_workflow_id(self):
        adapter = N8nAdapter()
        sig = inspect.signature(adapter._execute_workflow)
        assert "workflow_id" in sig.parameters
        # `workflow_id` MUST be keyword-only + no default so callers can't
        # accidentally fire an empty POST.
        p = sig.parameters["workflow_id"]
        assert p.default is inspect.Parameter.empty
        assert p.kind == inspect.Parameter.KEYWORD_ONLY


# --------------------------------------------------------------------------- #
# 2. FastAPI routes exist and are audited
# --------------------------------------------------------------------------- #
class TestN8nRoutes:
    def test_router_registers_all_expected_paths(self):
        from backend.api.workflows import router
        paths = {r.path for r in router.routes}
        assert "/api/workflows/n8n/status" in paths
        assert "/api/workflows/n8n/ping" in paths
        assert "/api/workflows/n8n/{workflow_id}/execute" in paths
        assert "/api/workflows/n8n/{workflow_id}/activate" in paths
        assert "/api/workflows/n8n/{workflow_id}/deactivate" in paths


class TestN8nRoutesLive:
    """Uses TestClient to actually invoke the endpoints without a running
    Uvicorn — verifies not-configured + error paths without a real n8n."""

    def _client(self):
        from fastapi.testclient import TestClient
        from backend.server import app
        return TestClient(app)

    def test_ping_without_config_returns_ok_false_and_readable_error(self):
        client = self._client()
        r = client.get("/api/workflows/n8n/ping")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["configured"] is False
        assert "N8N_BASE_URL" in body["error"]

    def test_execute_without_config_is_400_with_helpful_message(self):
        client = self._client()
        r = client.post("/api/workflows/n8n/wf-1/execute", json={})
        assert r.status_code == 400
        assert "not configured" in r.json()["detail"].lower()

    def test_activate_without_config_is_400(self):
        client = self._client()
        r = client.post("/api/workflows/n8n/wf-1/activate")
        assert r.status_code == 400


# --------------------------------------------------------------------------- #
# 3. Frontend n8n tab wiring
# --------------------------------------------------------------------------- #
class TestN8nTabWiring:
    def test_tab_exposes_test_connection_and_action_buttons(self):
        src = inspect.getsource(n8n_tab.build_tab)
        for eid in ("n8n-test-connection", "n8n-execute",
                    "n8n-activate", "n8n-deactivate", "n8n-picker"):
            assert eid in src, f"missing {eid} in build_tab"

    def test_execute_helper_hits_execute_endpoint(self, monkeypatch):
        captured = {}
        def fake_post(path, **kw):
            captured["path"] = path
            captured["json"] = kw.get("json")
            return {"ok": True, "workflow_id": "abc", "result": {}}
        monkeypatch.setattr(n8n_tab, "post", fake_post)
        msg = n8n_tab._execute("abc", "")
        assert "abc" in msg and "succeeded" in msg
        assert captured["path"] == "/api/workflows/n8n/abc/execute"

    def test_execute_helper_refuses_empty_workflow_id(self):
        assert n8n_tab._execute("", "").startswith("❌")

    def test_test_connection_shows_green_banner_on_success(self, monkeypatch):
        monkeypatch.setattr(n8n_tab, "get", lambda *a, **kw: {
            "ok": True, "configured": True, "base_url": "http://n8n:5678",
            "status_code": 200, "latency_ms": 12.3,
        })
        msg = n8n_tab._test_connection()
        assert msg.startswith("✅")
        assert "http://n8n:5678" in msg
        assert "12.3" in msg

    def test_test_connection_shows_red_banner_on_error(self, monkeypatch):
        monkeypatch.setattr(n8n_tab, "get", lambda *a, **kw: {
            "ok": False, "configured": True, "base_url": "http://x",
            "error": "Connection refused",
        })
        msg = n8n_tab._test_connection()
        assert msg.startswith("❌")
        assert "Connection refused" in msg

    def test_test_connection_shows_warn_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(n8n_tab, "get", lambda *a, **kw: {
            "ok": False, "configured": False, "error": "N8N_BASE_URL missing",
        })
        msg = n8n_tab._test_connection()
        assert msg.startswith("⚠️")


# --------------------------------------------------------------------------- #
# 4. progress.bind_stream_id / current_stream_id ContextVar
# --------------------------------------------------------------------------- #
class TestProgressStreamIdContext:
    def test_default_is_none(self):
        assert progress.current_stream_id() is None

    def test_bind_sets_and_restores(self):
        assert progress.current_stream_id() is None
        with progress.bind_stream_id("sid-abc"):
            assert progress.current_stream_id() == "sid-abc"
        # Reset after the with block exits.
        assert progress.current_stream_id() is None

    def test_binds_across_async_awaits(self):
        async def _inner():
            return progress.current_stream_id()

        async def _outer():
            with progress.bind_stream_id("sid-async"):
                # Value must survive an ``await`` point.
                got = await _inner()
                return got

        assert asyncio.run(_outer()) == "sid-async"


# --------------------------------------------------------------------------- #
# 5. BaseAgent streaming vs one-shot LLM path
# --------------------------------------------------------------------------- #
class TestBaseAgentStreamingSwitch:
    def _agent(self):
        from backend.agents.base import BaseAgent
        class _A(BaseAgent):
            name = "test_agent"
        return _A(system_prompt="s")

    def test_no_stream_id_uses_send_message(self):
        agent = self._agent()

        chat = AsyncMock()
        chat.send_message = AsyncMock(return_value="one-shot reply")

        class _UserMessage:
            def __init__(self, text): self.text = text

        async def _run():
            return await agent._invoke_llm(chat, _UserMessage, "hi")

        got = asyncio.run(_run())
        assert got == "one-shot reply"
        chat.send_message.assert_awaited_once()

    def test_stream_id_uses_stream_message(self):
        agent = self._agent()

        # Fake TextDelta events + a StreamDone-ish trailer we ignore.
        class _Delta:
            def __init__(self, content):
                self.content = content

        async def fake_stream(msg):
            for tok in ["hello ", "world", "!"]:
                yield _Delta(tok)

        chat = AsyncMock()
        chat.stream_message = fake_stream  # returns async iterator
        chat.send_message = AsyncMock(side_effect=AssertionError(
            "streaming path should NOT call send_message"))

        class _UserMessage:
            def __init__(self, text): self.text = text

        published: list[dict] = []
        original_publish = progress.publish

        async def _capture(*args, **kwargs):
            published.append({"agent": kwargs.get("agent"),
                              "kind": kwargs.get("kind"),
                              "detail": kwargs.get("detail")})

        async def _run():
            # Prime a stream so the code path picks streaming.
            sid = await progress.create_stream()
            with progress.bind_stream_id(sid):
                # Swap publish for a capture so we don't need a subscriber.
                progress.publish = _capture       # type: ignore[assignment]
                try:
                    reply = await agent._invoke_llm(chat, _UserMessage, "hi")
                finally:
                    progress.publish = original_publish  # type: ignore[assignment]
                    await progress.discard(sid)
            return reply

        got = asyncio.run(_run())
        assert got == "hello world!"
        # At least one publish must be `kind="token"` on the streaming path.
        token_events = [p for p in published if p["kind"] == "token"]
        assert token_events, f"no kind=token published; events={published}"
        assert all(p["agent"] == "test_agent" for p in token_events)


# --------------------------------------------------------------------------- #
# 6. Frontend _render_progress live-LLM section + token consumer
# --------------------------------------------------------------------------- #
class TestRenderProgressLLMSection:
    def test_no_llm_stream_no_section(self):
        state = pg._initial_progress_state()
        out = pg._render_progress(state)
        assert "Live LLM output" not in out

    def test_with_llm_stream_adds_section_and_tail(self):
        state = pg._initial_progress_state()
        stream = "x" * 3000       # deliberately longer than the 1500 cap
        out = pg._render_progress(state, llm_stream=stream)
        assert "Live LLM output" in out
        # Tail must be capped to 1500 chars — full stream not repeated.
        # Count `x`s after the "Live LLM output" marker.
        marker = out.index("Live LLM output")
        assert out.count("x", marker) == 1500


class TestGenerateConsumesTokenEvents:
    def test_token_events_accumulate_into_progress_markdown(self, monkeypatch):
        events = [
            {"kind": "agent", "agent": "pipeline_planning",
             "status": "running", "detail": "started"},
            {"kind": "token", "agent": "pipeline_planning",
             "status": "running", "detail": "Hello "},
            {"kind": "token", "agent": "pipeline_planning",
             "status": "running", "detail": "world"},
            {"kind": "result", "payload": {
                "pipeline": {"yaml_content": "stages: []", "filename": "x.yml"},
                "explanation": "e", "plan": {}, "validation": {},
                "analysis": {"owner": "o", "name": "n"},
                "generation_seconds": 0.4,
            }},
            {"kind": "done"},
        ]

        def fake_sse(path, *, json_body, **_kw):
            yield from events

        monkeypatch.setattr(pg, "sse_post", fake_sse)

        frames = list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "github_actions", "aws", "unspecified", "all_in_one", "", "terraform", "",
        ))

        # After the two token events, the progress markdown must include
        # the accumulated string.
        token_frames = [f for f in frames if "Live LLM output" in f[1]]
        assert token_frames, "no frame contained the Live LLM output section"
        last_token_frame = token_frames[-1]
        assert "Hello world" in last_token_frame[1]

    def test_new_agent_running_resets_buffer(self, monkeypatch):
        events = [
            {"kind": "agent", "agent": "repository_analysis",
             "status": "running", "detail": ""},
            {"kind": "token", "agent": "repository_analysis",
             "status": "running", "detail": "aaa"},
            # Agent transition → buffer must reset before we see bbb.
            {"kind": "agent", "agent": "pipeline_planning",
             "status": "running", "detail": ""},
            {"kind": "token", "agent": "pipeline_planning",
             "status": "running", "detail": "bbb"},
            {"kind": "result", "payload": {
                "pipeline": {"yaml_content": "", "filename": "x.yml"},
                "explanation": "", "plan": {}, "validation": {},
                "analysis": {"owner": "o", "name": "n"},
                "generation_seconds": 0.0,
            }},
            {"kind": "done"},
        ]

        def fake_sse(path, *, json_body, **_kw):
            yield from events

        monkeypatch.setattr(pg, "sse_post", fake_sse)

        frames = list(pg._generate(
            "https://github.com/o/n", "ghp_x", "main",
            "github_actions", "aws", "unspecified", "all_in_one", "", "terraform", "",
        ))
        # The last "Live LLM output" frame must contain only `bbb` — the
        # first agent's `aaa` was cleared when the second agent started.
        token_frames = [f for f in frames if "Live LLM output" in f[1]]
        last = token_frames[-1][1]
        assert "bbb" in last
        marker = last.index("Live LLM output")
        assert "aaa" not in last[marker:]
