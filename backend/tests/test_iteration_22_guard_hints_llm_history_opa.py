"""Iteration-22 tests — MCP guard, target hints, LLM history endpoint, OPA bundle."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.mcp.guard import (
    MCPGuardError,
    bind_agent,
    check,
    current_agent,
    enforce_mode,
)
from backend.services.target_hints import (
    HINTS,
    explanation_section,
    get_hint,
    header_comment,
)


# ---------------------------------------------------------------------------
# MCP GUARD
# ---------------------------------------------------------------------------
class TestMCPGuard:
    def test_no_agent_context_is_permissive(self):
        # API-layer callers have no agent context — must NOT be blocked.
        assert current_agent() is None
        check("github")     # no exception

    def test_declared_adapter_is_allowed(self):
        with bind_agent("repository_analysis"):
            check("github")     # repository_analysis lists github in reads_mcp

    def test_undeclared_adapter_is_blocked(self):
        with bind_agent("technology_detection"):     # declares no MCP
            with pytest.raises(MCPGuardError):
                check("github")

    def test_unknown_agent_name_is_blocked(self):
        with bind_agent("i_do_not_exist"):
            with pytest.raises(MCPGuardError):
                check("github")

    def test_warn_mode_allows(self, monkeypatch):
        monkeypatch.setenv("AIPP_MCP_GUARD", "warn")
        assert enforce_mode() == "warn"
        with bind_agent("technology_detection"):
            check("github")     # would be blocked in block mode

    def test_context_stacks_correctly(self):
        with bind_agent("repository_analysis"):
            assert current_agent() == "repository_analysis"
            with bind_agent("pipeline_doctor_rca"):
                assert current_agent() == "pipeline_doctor_rca"
            # after inner exit, outer restored
            assert current_agent() == "repository_analysis"
        assert current_agent() is None


class TestMCPClientGuardIntegration:
    """The guard must actually fire inside `MCPClient.call()`."""

    def test_client_call_blocked_from_wrong_agent(self):
        from backend.mcp.client import MCPClient

        client = MCPClient()

        async def run():
            with bind_agent("technology_detection"):     # no MCP declared
                with pytest.raises(MCPGuardError):
                    await client.call("github", "list_files", url="x", pat="y")

        asyncio.run(run())


# ---------------------------------------------------------------------------
# TARGET HINTS
# ---------------------------------------------------------------------------
class TestTargetHints:
    def test_unspecified_has_no_hint(self):
        assert get_hint("unspecified") is None
        assert header_comment("unspecified") == ""
        assert explanation_section("unspecified") == ""

    def test_every_target_has_a_hint(self):
        from backend.models.pipeline import CLOUD_TARGETS
        all_targets = {t for tgs in CLOUD_TARGETS.values() for t in tgs}
        for t in all_targets:
            assert t in HINTS, f"missing hint for {t}"

    def test_hint_shape(self):
        h = get_hint("aws_eks")
        assert h is not None
        assert h.label == "AWS EKS"
        assert "kubectl" in h.deploy_command
        assert h.prereq

    def test_header_comment_is_yaml_safe(self):
        c = header_comment("azure_webapp")
        assert c.startswith("# ─── AIPP Deployment Target")
        assert "az webapp" in c
        # Every non-empty line must start with `#` so it's a valid YAML comment.
        for line in c.splitlines():
            if line.strip():
                assert line.startswith("#"), f"non-comment line leaked: {line!r}"

    def test_explanation_section_names_the_target(self):
        s = explanation_section("gcp_cloud_run")
        assert "Google Cloud Run" in s
        assert "gcloud run deploy" in s


# ---------------------------------------------------------------------------
# LLM HISTORY ENDPOINT
# ---------------------------------------------------------------------------
class TestLLMHistoryEndpoint:
    def test_endpoint_is_registered(self):
        """We just need to confirm the route exists on the app — hitting it
        needs a real Postgres and is covered by the live smoke test."""
        from backend.server import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/llm/usage/history" in paths


# ---------------------------------------------------------------------------
# OPA STARTER BUNDLE
# ---------------------------------------------------------------------------
class TestOPABundle:
    ROOT = Path("/app/policy")

    def test_root_has_readme(self):
        assert (self.ROOT / "README.md").exists()

    def test_all_three_clouds_have_folders(self):
        for cloud in ("aws", "azure", "gcp"):
            assert (self.ROOT / cloud).is_dir(), f"missing {cloud} folder"

    def test_every_cloud_ships_four_rules(self):
        expected = {
            "deny-public-storage.rego",
            "deny-ssh-open-world.rego",
            "require-encryption.rego",
            "require-owner-tag.rego",
        }
        for cloud in ("aws", "azure", "gcp"):
            files = {p.name for p in (self.ROOT / cloud).iterdir() if p.suffix == ".rego"}
            assert expected.issubset(files), f"{cloud} missing: {expected - files}"

    def test_rego_files_have_package_directive(self):
        for rego in self.ROOT.rglob("*.rego"):
            src = rego.read_text()
            assert src.startswith("# ") or "package " in src, (
                f"{rego} lacks a top comment/package directive"
            )
            assert "package terraform." in src, (
                f"{rego} is not namespaced under `terraform.*`"
            )
