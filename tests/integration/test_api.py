"""Integration tests hitting the running FastAPI instance."""

from __future__ import annotations

import os

import httpx
import pytest

BASE = os.environ.get("AIPP_INTEGRATION_URL", "http://127.0.0.1:8001")


def test_root_returns_service_info():
    r = httpx.get(f"{BASE}/api/", timeout=10)
    r.raise_for_status()
    data = r.json()
    assert data["service"] == "AIPP"
    assert "github" in data["configured_mcp_adapters"]


def test_health_ok():
    r = httpx.get(f"{BASE}/api/health", timeout=10)
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_mcp_tools_lists_all_platforms():
    r = httpx.get(f"{BASE}/api/mcp/tools", timeout=10)
    tools = r.json()
    for name in ["github", "n8n", "azure_devops", "gitlab", "harness", "tekton",
                 "kubernetes", "azure", "aws", "gcp"]:
        assert name in tools


def test_n8n_status_returns_not_configured_when_creds_missing():
    r = httpx.get(f"{BASE}/api/workflows/n8n/status", timeout=10)
    data = r.json()
    # When N8N_BASE_URL/N8N_API_KEY are absent we must NOT hallucinate — expect configured=False.
    if not os.environ.get("N8N_BASE_URL") or not os.environ.get("N8N_API_KEY"):
        assert data["configured"] is False


def test_research_metrics_shape():
    r = httpx.get(f"{BASE}/api/research/metrics", timeout=10)
    data = r.json()
    for k in ("pipeline_runs", "rca_reports", "avg_generation_seconds", "avg_rca_confidence"):
        assert k in data


def test_pipeline_generate_requires_pat():
    r = httpx.post(
        f"{BASE}/api/pipelines/generate",
        json={"repo_url": "https://github.com/foo/bar", "github_pat": "short",
              "branch": "main", "ci_platform": "github_actions", "cloud_platform": "azure"},
        timeout=15,
    )
    # min_length=8 on the field → 422
    assert r.status_code in (400, 422)


def test_rca_requires_input():
    r = httpx.post(f"{BASE}/api/pipeline-doctor/analyze",
                   data={"ci_platform": "github_actions"}, timeout=15)
    assert r.status_code == 400
