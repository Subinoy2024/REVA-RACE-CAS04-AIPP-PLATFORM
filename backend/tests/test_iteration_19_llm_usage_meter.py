"""Iteration-19 regression tests — LLM usage / spend tracker in the UI.

User asked: "LLM budget or user's own OpenAI/Anthropic/Gemini key for the
22-repo benchmark run — can we add in the UI, how much spend or utilize?"

Implementation:
  1. `backend/services/llm_usage.py` — process-wide tracker; records
     char lengths per LLM call, converts to token estimates (~4 chars/tok)
     and $ estimates via a per-model price table.
  2. `backend/agents/base.py` — records every LLM call automatically.
  3. `GET /api/llm/usage` — returns totals + per-model breakdown.
  4. `POST /api/llm/usage/reset` — zero counters (useful pre-batch).
  5. Gradio "LLM usage & estimated spend" accordion in the Generator tab
     with Refresh + Reset buttons. Auto-refreshes after each Generate.
"""

from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

from backend.server import app
from backend.services import llm_usage
from backend.services.llm_usage import (
    LLMUsageTracker, PRICE_TABLE, _chars_to_tokens, _estimate_cost_usd,
)
from frontend.tabs import pipeline_generator as pg


# ---------------------------------------------------------------------------
# 1. Cost / token math helpers
# ---------------------------------------------------------------------------
class TestTokenizationAndPricing:
    def test_chars_to_tokens_uses_four_char_heuristic(self):
        # 4 chars ≈ 1 token
        assert _chars_to_tokens(0) == 0
        assert _chars_to_tokens(3) == 0     # <4 rounds down
        assert _chars_to_tokens(4) == 1
        assert _chars_to_tokens(400) == 100

    def test_price_table_covers_common_models(self):
        for model in ["gpt-4o-mini", "gpt-4o", "claude-sonnet-4-5",
                      "gemini-1.5-flash"]:
            assert model in PRICE_TABLE, f"{model} missing from price table"

    def test_cost_estimate_for_known_model(self):
        # 1M in + 1M out for gpt-4o-mini = $0.15 + $0.60 = $0.75
        cost = _estimate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000)
        assert abs(cost - 0.75) < 1e-6

    def test_unknown_model_uses_fallback(self):
        cost_known = _estimate_cost_usd("gpt-4o-mini", 100_000, 100_000)
        cost_unknown = _estimate_cost_usd("some-experimental-model",
                                          100_000, 100_000)
        # Unknown model must return a positive fallback estimate, not zero.
        assert cost_unknown > 0
        # Fallback ($2 + $8)/M > gpt-4o-mini ($0.15 + $0.60)/M
        assert cost_unknown > cost_known


# ---------------------------------------------------------------------------
# 2. LLMUsageTracker mechanics
# ---------------------------------------------------------------------------
class TestTracker:
    def test_record_increments_totals(self):
        t = LLMUsageTracker()
        t.record(agent="repo", provider="openai", model="gpt-4o-mini",
                 prompt_chars=800, completion_chars=200)
        totals = t.totals()
        assert totals["total_calls"] == 1
        assert totals["total_prompt_tokens"] == 200
        assert totals["total_completion_tokens"] == 50
        assert totals["total_tokens"] == 250
        assert totals["estimated_cost_usd"] > 0

    def test_two_calls_aggregate_per_model(self):
        t = LLMUsageTracker()
        t.record(agent="a1", provider="openai", model="gpt-4o-mini",
                 prompt_chars=400, completion_chars=100)
        t.record(agent="a2", provider="openai", model="gpt-4o-mini",
                 prompt_chars=800, completion_chars=200)
        totals = t.totals()
        assert totals["total_calls"] == 2
        assert "gpt-4o-mini" in totals["by_model"]
        assert totals["by_model"]["gpt-4o-mini"]["calls"] == 2

    def test_reset_clears_all_calls(self):
        t = LLMUsageTracker()
        t.record(agent="x", provider="p", model="gpt-4o-mini",
                 prompt_chars=100, completion_chars=50)
        assert t.totals()["total_calls"] == 1
        t.reset()
        assert t.totals()["total_calls"] == 0
        assert t.totals()["by_model"] == {}

    def test_singleton_tracker_returned(self):
        assert llm_usage.tracker() is llm_usage.tracker()


# ---------------------------------------------------------------------------
# 3. FastAPI endpoints
# ---------------------------------------------------------------------------
class TestLLMUsageEndpoints:
    def _client(self):
        # Ensure clean state for endpoint tests.
        llm_usage.tracker().reset()
        return TestClient(app)

    def test_get_usage_returns_totals_dict(self):
        client = self._client()
        r = client.get("/api/llm/usage")
        assert r.status_code == 200
        body = r.json()
        for key in ["total_calls", "total_tokens", "estimated_cost_usd",
                    "by_model", "note"]:
            assert key in body

    def test_reset_endpoint_zeros_counters(self):
        client = self._client()
        # Record a call directly on the singleton — endpoint should reset it.
        llm_usage.tracker().record(
            agent="tst", provider="openai", model="gpt-4o-mini",
            prompt_chars=400, completion_chars=100,
        )
        assert client.get("/api/llm/usage").json()["total_calls"] == 1

        r = client.post("/api/llm/usage/reset")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert client.get("/api/llm/usage").json()["total_calls"] == 0


# ---------------------------------------------------------------------------
# 4. Gradio panel — render helper + wiring
# ---------------------------------------------------------------------------
class TestUsagePanelUI:
    def test_render_totals_shows_dollar_estimate(self):
        totals = {
            "total_calls": 5, "total_tokens": 1234,
            "estimated_cost_usd": 0.0123,
            "by_model": {"gpt-4o-mini": {"calls": 5, "prompt_tokens": 1000,
                                          "completion_tokens": 234,
                                          "cost_usd": 0.0123}},
            "note": "Estimated.",
        }
        md = pg._render_usage_totals(totals)
        assert "0.0123" in md
        assert "gpt-4o-mini" in md
        assert "1,234" in md          # thousands separator
        assert "Estimated" in md

    def test_render_totals_empty_state_hints_user(self):
        md = pg._render_usage_totals(
            {"total_calls": 0, "total_tokens": 0,
             "estimated_cost_usd": 0.0, "by_model": {}, "note": "Estimated."}
        )
        assert "No LLM calls yet" in md

    def test_build_tab_declares_usage_accordion(self):
        src = inspect.getsource(pg.build_tab)
        assert "pg-llm-usage-accordion" in src
        assert "pg-llm-usage" in src
        assert "pg-usage-refresh" in src
        assert "pg-usage-reset" in src

    def test_click_wiring_auto_refreshes_usage_after_generate(self):
        src = inspect.getsource(pg.build_tab)
        # `btn.click(_refresh_usage, ...)` right after the generate click
        # keeps the usage badge fresh without an extra button press.
        assert "_refresh_usage" in src
        assert "_reset_usage" in src
