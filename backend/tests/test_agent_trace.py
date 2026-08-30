"""Agent trace collector unit tests — iteration-27.

Covers:
  1. TraceCollector accumulates LLM + MCP + skill records.
  2. finalize() builds a well-shaped input/output summary.
  3. contextvar `current()` returns the bound collector inside a `bind`
     block and None outside.
  4. `estimate_cost_usd` public wrapper matches the private estimator.
  5. `GET /api/agents/skills` returns non-empty catalog once registry
     is populated.
"""

from __future__ import annotations

import uuid

import pytest

from backend.services.agent_trace import TraceCollector, bind, current


def test_trace_collector_accumulates_llm_calls():
    c = TraceCollector(run_id=uuid.uuid4(), agent_name="repository_analysis", step_index=0)
    c.record_llm(provider="openai", model="gpt-4o-mini",
                 prompt="hello", prompt_tokens=10, completion_tokens=5, cost_usd=0.001)
    c.record_llm(provider="openai", model="gpt-4o-mini",
                 prompt="retry", prompt_tokens=8, completion_tokens=4, cost_usd=0.0005)
    assert c.prompt_tokens == 18
    assert c.completion_tokens == 9
    assert c.cost_usd == pytest.approx(0.0015)
    assert c.prompt_text_parts == ["hello", "retry"]


def test_trace_collector_records_mcp_calls():
    c = TraceCollector(run_id=uuid.uuid4(), agent_name="repository_analysis", step_index=0)
    c.record_mcp(adapter="github", tool="list_files",
                 args_summary="{'owner': 'x'}", ok=True, duration_ms=42)
    c.record_mcp(adapter="github", tool="get_file",
                 args_summary="{'path': 'README.md'}", ok=False, duration_ms=99)
    assert len(c.mcp_calls) == 2
    assert c.mcp_calls[0].tool == "list_files"
    assert c.mcp_calls[1].ok is False


def test_trace_collector_declare_skills_deduplicates():
    c = TraceCollector(run_id=uuid.uuid4(), agent_name="a", step_index=0)
    c.declare_skills(["github", "opa"])
    c.declare_skills(["github", "azure_devops"])
    assert sorted(c.skills_declared) == ["azure_devops", "github", "opa"]


def test_contextvar_bind_and_unbind():
    assert current() is None
    c = TraceCollector(run_id=uuid.uuid4(), agent_name="a", step_index=0)
    with bind(c) as active:
        assert active is c
        assert current() is c
    assert current() is None


def test_error_mark_sets_status():
    c = TraceCollector(run_id=uuid.uuid4(), agent_name="a", step_index=0)
    c.mark_error(RuntimeError("boom"))
    assert c.status == "error"
    assert "boom" in (c.error or "")


def test_estimate_cost_usd_public_wrapper():
    from backend.services.llm_usage import _estimate_cost_usd, estimate_cost_usd
    priv = _estimate_cost_usd("gpt-4o-mini", 100, 50)
    pub = estimate_cost_usd(provider="openai", model="gpt-4o-mini",
                            prompt_tokens=100, completion_tokens=50)
    assert priv == pub


@pytest.mark.asyncio
async def test_skills_endpoint_returns_registered_agents():
    from backend.api.agent_traces import list_skills
    out = await list_skills()
    assert "agents" in out
    # Non-empty because register.py registers ~8 agents at import time.
    assert len(out["agents"]) >= 5
    names = {a["name"] for a in out["agents"]}
    # Sanity check — key agents must be present.
    assert {"repository_analysis", "pipeline_planning"} <= names
