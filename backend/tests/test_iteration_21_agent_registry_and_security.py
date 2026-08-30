"""Iteration-21 tests — agent registry, deployment targets, rate limiter,
secret scanner."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.agents.registry import get_agent, list_agents, registry_size
from backend.core.rate_limit import RateLimiter
from backend.models.pipeline import CLOUD_TARGETS, DeploymentTarget
from backend.services.secret_scanner import scan, scan_report


class TestAgentRegistry:
    def test_registry_has_all_eight_agents(self):
        names = {a.name for a in list_agents()}
        assert names == {
            "repository_analysis",
            "technology_detection",
            "architecture_detection",
            "pipeline_planning",
            "environment_deployment",
            "pipeline_generation",
            "pipeline_validation",
            "pipeline_doctor_rca",
        }
        assert registry_size() == 8

    def test_each_agent_has_skills_and_outputs(self):
        for a in list_agents():
            assert a.skills, f"{a.name} has empty skills"
            assert a.outputs, f"{a.name} has no outputs model"
            assert a.description
            assert a.label

    def test_get_agent_lookup(self):
        a = get_agent("repository_analysis")
        assert a is not None
        assert "github" in a.reads_mcp

    def test_to_card_is_json_serialisable(self):
        import json
        for a in list_agents():
            card = a.to_card()
            json.dumps(card)   # no exception
            assert card["name"] == a.name
            assert isinstance(card["skills"], list)


class TestDeploymentTargets:
    def test_cloud_targets_covers_all_three_clouds(self):
        assert set(CLOUD_TARGETS.keys()) == {"aws", "azure", "gcp"}

    def test_each_cloud_has_at_least_four_options(self):
        for cloud, targets in CLOUD_TARGETS.items():
            assert len(targets) >= 4, f"{cloud} has too few deployment targets"

    def test_enum_covers_every_target(self):
        all_targets = {t for targets in CLOUD_TARGETS.values() for t in targets}
        enum_values = {m.value for m in DeploymentTarget}
        # every target in the matrix must exist as an enum member
        for t in all_targets:
            assert t in enum_values


class TestSecretScanner:
    def test_clean_yaml_is_clean(self):
        report = scan_report("stages:\n  - build\n  - test\n")
        assert report["clean"] is True
        assert report["blocked"] is False
        assert report["findings"] == []

    def test_github_pat_is_flagged(self):
        text = "TOKEN: ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD"
        r = scan_report(text)
        assert r["clean"] is False
        assert r["blocked"] is True
        assert any(f["kind"] == "github_pat" for f in r["findings"])

    def test_aws_access_key_is_flagged(self):
        r = scan_report('AWS_KEY: "AKIAIOSFODNN7EXAMPLE"')
        assert r["blocked"] is True
        assert any(f["kind"] == "aws_access_key" for f in r["findings"])

    def test_placeholder_is_not_flagged(self):
        # env-substitution placeholders and REPLACE_ME strings must be safe.
        r = scan_report("token: ${GITHUB_TOKEN}\nkey: REPLACE_ME_ghp_stub")
        assert r["clean"] is True

    def test_line_numbers_are_reported(self):
        text = "line one\nline two\nkey: ghp_" + "x" * 40
        r = scan_report(text)
        assert r["findings"][0]["line"] == 3


class TestRateLimiter:
    def test_within_limit_allows_calls(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        rl.check("k")
        rl.check("k")
        rl.check("k")   # third is still ok

    def test_exceeding_limit_raises_429(self):
        rl = RateLimiter(max_requests=2, window_seconds=60)
        rl.check("k"); rl.check("k")
        with pytest.raises(HTTPException) as exc:
            rl.check("k")
        assert exc.value.status_code == 429
        assert "Retry-After" in exc.value.headers

    def test_reset_clears_bucket(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.check("k")
        rl.reset("k")
        rl.check("k")   # no exception

    def test_per_key_isolation(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.check("A")
        rl.check("B")   # different key, still fine
        with pytest.raises(HTTPException):
            rl.check("A")


class TestAgentsEndpoint:
    def test_get_api_agents_returns_all_eight(self):
        from backend.server import app
        client = TestClient(app)
        r = client.get("/api/agents")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 8
        assert len(data["agents"]) == 8
        names = [a["name"] for a in data["agents"]]
        assert "repository_analysis" in names
        assert "pipeline_doctor_rca" in names


class TestDeploymentTargetsEndpoint:
    def test_get_deployment_targets_returns_all_three_clouds(self):
        from backend.server import app
        client = TestClient(app)
        r = client.get("/api/pipelines/deployment-targets")
        assert r.status_code == 200
        data = r.json()
        assert set(data["clouds"].keys()) == {"aws", "azure", "gcp"}
        # every cloud must include 'unspecified' as first option
        for _cloud, opts in data["clouds"].items():
            values = [o["value"] for o in opts]
            assert values[0] == "unspecified"


class TestCommitEndpointBlocksSecrets:
    def test_commit_with_gh_pat_in_yaml_returns_400(self):
        from backend.server import app
        client = TestClient(app)
        r = client.post("/api/deployment/commit", json={
            "repo_url": "https://github.com/owner/repo",
            "github_pat": "ghp_" + "x" * 40,
            "target_branch": "main",
            "ci_platform": "github_actions",
            "yaml_content": (
                "stages:\n"
                "  - name: deploy\n"
                # DELIBERATE secret: real-shape PAT baked into YAML.
                "    env:\n"
                "      SECRET: ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD\n"
            ),
            "commit_message": "test",
        })
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert detail["error"] == "secret_detected"
        assert detail["findings"]
