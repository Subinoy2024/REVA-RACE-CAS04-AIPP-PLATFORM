"""AIPP backend integration tests (pytest).

Covers all endpoints listed in the E1 review-request:
  - /api/, /api/health, /api/mcp/tools
  - /api/workflows/n8n/status
  - /api/research/{metrics,audit,experiments}
  - /api/pipelines/{runs,generate}
  - /api/pipeline-doctor/{reports,analyze}
  - /api/repositories/probe

Base URL is taken from env; defaults to the internal supervisor-managed backend so
these tests behave identically whether pointed at the preview URL or 127.0.0.1.

NOTE: The Emergent Universal LLM Key budget is tiny ($0.001) and typically already
exhausted; LLM-hitting endpoints are asserted to return a **clean 502** with the
string 'LLM error' in `detail` (i.e. no unhandled 500 traceback). We accept a
successful 200 as well should the budget be replenished.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

# ---- Config ----
BASE = os.environ.get("AIPP_INTEGRATION_URL", "http://127.0.0.1:8001").rstrip("/")
TIMEOUT = 60


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=TIMEOUT) as c:
        yield c


# --------------------------------------------------------------------------- #
# Root / health / MCP discovery
# --------------------------------------------------------------------------- #
class TestServiceInfo:
    def test_root_service_info(self, client):
        r = client.get("/api/")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "AIPP"
        assert "configured_mcp_adapters" in data
        assert "github" in data["configured_mcp_adapters"]

    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_mcp_tools_all_11_adapters(self, client):
        r = client.get("/api/mcp/tools")
        assert r.status_code == 200
        tools = r.json()
        expected = [
            "github", "n8n", "azure_devops", "gitlab", "github_actions",
            "harness", "tekton", "kubernetes", "azure", "aws", "gcp",
        ]
        for name in expected:
            assert name in tools, f"Missing MCP adapter: {name}"
            # each adapter must expose a non-empty list of tool names
            assert isinstance(tools[name], list) and len(tools[name]) > 0


# --------------------------------------------------------------------------- #
# n8n status
# --------------------------------------------------------------------------- #
class TestN8nStatus:
    def test_n8n_status_not_configured(self, client):
        r = client.get("/api/workflows/n8n/status")
        assert r.status_code == 200
        data = r.json()
        # env has empty N8N_BASE_URL/N8N_API_KEY -> configured must be False
        if not os.environ.get("N8N_BASE_URL") or not os.environ.get("N8N_API_KEY"):
            assert data["configured"] is False
            assert data.get("reason"), "Must include a helpful reason when not configured"
            assert data.get("workflows") == []  # no mocks


# --------------------------------------------------------------------------- #
# Research
# --------------------------------------------------------------------------- #
class TestResearch:
    def test_metrics_shape(self, client):
        r = client.get("/api/research/metrics")
        assert r.status_code == 200
        data = r.json()
        for k in ("pipeline_runs", "rca_reports",
                  "avg_generation_seconds", "avg_rca_confidence"):
            assert k in data
        assert isinstance(data["pipeline_runs"], int)
        assert isinstance(data["rca_reports"], int)

    def test_audit_returns_list(self, client):
        r = client.get("/api/research/audit")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_experiment_create_then_list_persistence(self, client):
        """Create → GET verification. Validates PostgreSQL persistence."""
        marker = f"TEST_{uuid.uuid4().hex[:12]}"
        payload = {
            "experiment_type": "aipp",
            "ci_platform": "github_actions",
            "repository_url": f"https://github.com/example/{marker}",
            "metrics": {"duration_seconds": 1.23, "marker": marker},
            "notes": f"integration test {marker}",
        }
        r = client.post("/api/research/experiments", json=payload)
        assert r.status_code == 200, r.text
        created = r.json()
        assert "id" in created and created["id"]
        exp_id = created["id"]

        # verify it comes back in the list (persisted via SQLAlchemy → Postgres)
        r2 = client.get("/api/research/experiments")
        assert r2.status_code == 200
        rows = r2.json()
        matches = [row for row in rows if row["id"] == exp_id]
        assert len(matches) == 1, f"Experiment {exp_id} not returned by list"
        row = matches[0]
        assert row["experiment_type"] == "aipp"
        assert row["ci_platform"] == "github_actions"
        assert row["repository_url"] == payload["repository_url"]
        assert row["metrics"]["marker"] == marker
        assert row["notes"] == payload["notes"]
        assert "created_at" in row and row["created_at"]


# --------------------------------------------------------------------------- #
# Pipelines
# --------------------------------------------------------------------------- #
class TestPipelines:
    def test_runs_empty_list(self, client):
        r = client.get("/api/pipelines/runs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_run_not_found_returns_404(self, client):
        bogus = "00000000-0000-0000-0000-000000000000"
        r = client.get(f"/api/pipelines/runs/{bogus}")
        assert r.status_code == 404
        assert "detail" in r.json()

    def test_generate_validation_short_pat(self, client):
        r = client.post(
            "/api/pipelines/generate",
            json={
                "repo_url": "https://github.com/foo/bar",
                "github_pat": "short",   # 5 chars < min_length=8
                "branch": "main",
                "ci_platform": "github_actions",
                "cloud_platform": "azure",
            },
        )
        assert r.status_code == 422, r.text
        body = r.json()
        assert "detail" in body
        # ensure the failure references the pat field
        details = body["detail"] if isinstance(body["detail"], list) else [body["detail"]]
        assert any(
            "github_pat" in str(d) or "min_length" in str(d) or "at least 8" in str(d)
            for d in details
        )

    def test_generate_clean_error_on_llm_or_repo_failure(self, client):
        """With a bogus PAT the flow will fail at repo probe (400) or (if it got
        further) at LLM call (502). What we assert is: NO unhandled 500 with a
        raw traceback."""
        r = client.post(
            "/api/pipelines/generate",
            json={
                "repo_url": "https://github.com/octocat/Hello-World",
                "github_pat": "ghp_bogusbogusbogusbogusbogus",
                "branch": "main",
                "ci_platform": "github_actions",
                "cloud_platform": "azure",
            },
        )
        assert r.status_code in (400, 502), r.text
        body = r.json()
        assert "detail" in body and body["detail"]
        # not an unhandled traceback
        assert "Traceback" not in str(body["detail"])


# --------------------------------------------------------------------------- #
# Pipeline Doctor (RCA)
# --------------------------------------------------------------------------- #
class TestPipelineDoctor:
    def test_reports_empty_list(self, client):
        r = client.get("/api/pipeline-doctor/reports")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_analyze_requires_log(self, client):
        r = client.post(
            "/api/pipeline-doctor/analyze",
            data={"ci_platform": "github_actions"},
        )
        assert r.status_code == 400
        assert "raw_log" in r.json()["detail"].lower() or "log" in r.json()["detail"].lower()

    def test_analyze_rejects_too_short_log(self, client):
        r = client.post(
            "/api/pipeline-doctor/analyze",
            data={"ci_platform": "github_actions", "raw_log": "short"},
        )
        assert r.status_code == 400
        assert "too short" in r.json()["detail"].lower()

    def test_analyze_reasonable_log_returns_report_or_clean_502(self, client):
        long_log = (
            "ERROR: npm ERR! code ELIFECYCLE\n"
            "npm ERR! errno 1\n"
            "npm ERR! test@1.0.0 build: `webpack`\n"
            "npm ERR! Exit status 1\n"
            "npm ERR! Failed at the test@1.0.0 build script.\n"
        ) * 4  # ~600 chars

        r = client.post(
            "/api/pipeline-doctor/analyze",
            data={"ci_platform": "github_actions", "raw_log": long_log},
            timeout=90,
        )
        assert r.status_code in (200, 502), r.text
        ctype = r.headers.get("content-type", "")
        if r.status_code == 502:
            # App-level 502 is JSON with 'LLM error'. Preview URL may have its
            # Cloudflare edge rewrite the 502 into an HTML 'Bad gateway' page –
            # that is an *infra* concern, not a backend defect, so allow it.
            if "application/json" in ctype:
                body = r.json()
                assert "LLM error" in body.get("detail", "")
                assert "Traceback" not in body["detail"]
            else:
                # Cloudflare edge 502 HTML — verify it is not an app traceback
                assert "Traceback" not in r.text
        else:
            body = r.json()
            # Successful RCA — validate schema.
            for k in ("id", "ci_platform", "failed_stage", "root_cause",
                      "confidence", "evidence", "corrective_actions",
                      "preventive_actions"):
                assert k in body, f"Missing key {k} in RCA response"
            assert isinstance(body["evidence"], list)
            assert isinstance(body["corrective_actions"], list)
            assert isinstance(body["preventive_actions"], list)
            assert 0.0 <= float(body["confidence"]) <= 1.0


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #
class TestRepositories:
    def test_probe_bogus_pat_returns_structured_400(self, client):
        r = client.post(
            "/api/repositories/probe",
            json={
                "repo_url": "https://github.com/octocat/Hello-World",
                "github_pat": "ghp_bogusbogusbogusbogusbogus",
                "branch": "main",
            },
        )
        assert r.status_code == 400, r.text
        body = r.json()
        assert "detail" in body and body["detail"]
        assert "Traceback" not in str(body["detail"])
