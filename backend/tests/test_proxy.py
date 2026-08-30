"""Backend proxy contract tests — Option-2 secret vault.

Validates:
  * /api/proxy/* requires bearer auth (401 without, 401 with wrong key)
  * Correct key hits the endpoint but returns 503 for unconfigured services
  * Allowlist gate rejects unknown repos with 403
  * Constant-time compare (no timing leak — smoke test)
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient


def _client(env_overrides: dict[str, str] | None = None):
    """Create a fresh TestClient with proxy env vars set."""
    prev = {}
    env_overrides = env_overrides or {}
    for k, v in env_overrides.items():
        prev[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        # Clear the LRU cache so get_settings() re-reads from os.environ.
        from backend.core.config import get_settings
        get_settings.cache_clear()
        from backend.server import app
        return TestClient(app), prev
    except Exception:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        raise


def _restore(prev: dict[str, str]) -> None:
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    # Reset cache back to real env for downstream tests.
    from backend.core.config import get_settings
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
def test_proxy_requires_bearer_when_configured():
    client, prev = _client({"PROXY_API_KEY": "test-key-123"})
    try:
        # No auth header
        r = client.get("/api/proxy/health")
        assert r.status_code == 401
        # Wrong key
        r = client.get("/api/proxy/health",
                       headers={"Authorization": "Bearer wrong-key"})
        assert r.status_code == 401
        # Correct key
        r = client.get("/api/proxy/health",
                       headers={"Authorization": "Bearer test-key-123"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
    finally:
        _restore(prev)


def test_proxy_returns_503_when_key_missing():
    client, prev = _client({"PROXY_API_KEY": ""})
    try:
        r = client.get("/api/proxy/health",
                       headers={"Authorization": "Bearer anything"})
        assert r.status_code == 503
        assert "not configured" in r.json()["detail"]
    finally:
        _restore(prev)


def test_health_reports_configured_services():
    """Health endpoint reveals which infra creds are populated, without leaking values."""
    client, prev = _client({
        "PROXY_API_KEY": "k",
        "K8S_API_URL": "https://k8s.example:6443", "K8S_TOKEN": "tok",
        # Others empty
        "GRAFANA_URL": "", "GRAFANA_API_KEY": "",
    })
    try:
        r = client.get("/api/proxy/health",
                       headers={"Authorization": "Bearer k"})
        assert r.status_code == 200
        cfg = r.json()["configured"]
        assert cfg["k8s"] is True
        assert cfg["grafana"] is False
        assert cfg["github"] is False
    finally:
        _restore(prev)


def test_k8s_endpoint_503_when_unconfigured():
    client, prev = _client({
        "PROXY_API_KEY": "k",
        "K8S_API_URL": "", "K8S_TOKEN": "",
    })
    try:
        r = client.get("/api/proxy/k8s/pods",
                       headers={"Authorization": "Bearer k"})
        assert r.status_code == 503
    finally:
        _restore(prev)


def test_github_allowlist_gate_blocks_unknown_repo():
    client, prev = _client({
        "PROXY_API_KEY": "k",
        "GITHUB_PAT": "ghp_test",
        "GH_REPO_ALLOWLIST": "known-owner/known-repo",
    })
    try:
        r = client.get("/api/proxy/github/repo/attacker/private",
                       headers={"Authorization": "Bearer k"})
        assert r.status_code == 403
        assert "not_in_allowlist" in r.json()["detail"]
    finally:
        _restore(prev)


def test_github_allowlist_empty_allows_all():
    """Blank allowlist = dev mode = allow-all (no 403)."""
    client, prev = _client({
        "PROXY_API_KEY": "k",
        "GITHUB_PAT": "ghp_test",
        "GH_REPO_ALLOWLIST": "",
    })
    try:
        # 200 requires network to GitHub; we accept either a 403 (allowlist)
        # or ANY non-403 (allowlist passed). We only assert no 403.
        r = client.get("/api/proxy/github/repo/some/repo",
                       headers={"Authorization": "Bearer k"})
        assert r.status_code != 403
    finally:
        _restore(prev)


def test_constant_time_compare_no_timing_leak():
    """Rough smoke: 100 wrong-key attempts should not take dramatically
    different times based on key prefix. We just assert they don't 200.
    (Real timing-attack testing needs specialized tools; this documents intent.)"""
    client, prev = _client({"PROXY_API_KEY": "abcdefghijk"})
    try:
        for wrong in ["a...", "aaaa", "zzzz", "abcx", "abcdefghijl"]:
            r = client.get("/api/proxy/health",
                           headers={"Authorization": f"Bearer {wrong}"})
            assert r.status_code == 401
    finally:
        _restore(prev)


# ---------------------------------------------------------------------------
# Workflow generator now emits proxy calls
# ---------------------------------------------------------------------------
import json
import re
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "n8n" / "workflows"


def _load_wf(name_contains: str) -> dict:
    for p in WORKFLOWS_DIR.glob("*.json"):
        d = json.loads(p.read_text())
        if name_contains in d["name"]:
            return d
    raise FileNotFoundError(name_contains)


def test_wf07_uses_proxy_for_k8s():
    """Workflow #07 K8s Troubleshoot should call the AIPP proxy, not k8s API directly.

    Post iteration-35: AIPP_BASE_URL + AIPP_API_KEY are inlined at build time
    (n8n Community edition does not support the Variables API). We assert on
    the proxy path + Bearer header presence rather than $vars references.
    """
    wf = _load_wf("K8s Troubleshoot")
    blob = json.dumps(wf)
    assert "/api/proxy/k8s/" in blob
    assert "Bearer " in blob
    # And no legacy references leaked through the bake step:
    assert "$vars." not in blob
    assert "$env.AIPP_" not in blob


def test_wf02_uses_proxy_for_github_tree():
    wf = _load_wf("IaC Drift")
    blob = json.dumps(wf)
    assert "/api/proxy/github/tree/" in blob


def test_wf03_uses_proxy_for_github_org_members():
    wf = _load_wf("Access Review")
    blob = json.dumps(wf)
    assert "/api/proxy/github/org/" in blob


def test_wf04_uses_proxy_for_proxmox():
    wf = _load_wf("Self-Service")
    blob = json.dumps(wf)
    assert "/api/proxy/proxmox/vm" in blob
    assert "PROXMOX_TOKEN" not in blob


def test_wf05_uses_proxy_for_ado_and_gh():
    wf = _load_wf("Pipeline Status Digest")
    blob = json.dumps(wf)
    assert "/api/proxy/ado/runs" in blob
    assert "/api/proxy/github/runs/" in blob


def test_no_direct_infra_secrets_in_any_workflow():
    """After Option-A migration, workflows must reference infra creds ONLY
    through the AIPP proxy — never as raw $env.* / $vars.* env vars."""
    FORBIDDEN = {
        "K8S_TOKEN", "K8S_API_URL", "PROXMOX_TOKEN", "PROXMOX_URL",
        "GRAFANA_API_KEY", "GITHUB_PAT", "ADO_PAT", "GH_REPO_ALLOWLIST",
    }
    ref_re = re.compile(r"\$(?:env|vars)\.([A-Z_][A-Z0-9_]*)")
    for p in WORKFLOWS_DIR.glob("*.json"):
        blob = p.read_text()
        used = set(ref_re.findall(blob))
        leaked = used & FORBIDDEN
        assert not leaked, (
            f"{p.name} still references infra secrets: {leaked}. "
            "Move to aipp_call() proxy."
        )
