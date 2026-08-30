"""Iteration-26 · GitLab Auto-Deploy writer — unit tests.

Uses `httpx.MockTransport` (no extra deps) via a monkeypatched
`httpx.AsyncClient` to hermetically test the URL/API contract without
hitting gitlab.com. Real end-to-end deploys are covered by the
live-backend suite behind an opt-in flag.
"""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

from backend.core.exceptions import RepositoryAccessError
from backend.services import gitlab_writer as gw


# ---------- URL parsing ----------------------------------------------------

def test_parse_saas_url():
    r = gw.parse_gitlab_url("https://gitlab.com/mygroup/myrepo")
    assert r.full_path == "mygroup/myrepo"
    assert r.api_base == "https://gitlab.com/api/v4"
    assert r.web_base == "https://gitlab.com/mygroup/myrepo"


def test_parse_url_strips_git_suffix():
    r = gw.parse_gitlab_url("https://gitlab.com/group/sub/repo.git")
    assert r.full_path == "group/sub/repo"


def test_parse_self_hosted():
    r = gw.parse_gitlab_url("https://gitlab.mycorp.com/ops/pipelines")
    assert r.api_base == "https://gitlab.mycorp.com/api/v4"
    assert r.full_path == "ops/pipelines"


def test_parse_rejects_top_level_url():
    with pytest.raises(RepositoryAccessError):
        gw.parse_gitlab_url("https://gitlab.com")
    with pytest.raises(RepositoryAccessError):
        gw.parse_gitlab_url("https://gitlab.com/onlygroup")


# ---------- HTTP mock harness ---------------------------------------------

def _install_mock(monkeypatch, handler: Callable[[httpx.Request], httpx.Response]):
    """Swap httpx.AsyncClient inside `gitlab_writer` with a mock-transport one."""
    transport = httpx.MockTransport(handler)

    class _MockedClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gw.httpx, "AsyncClient", _MockedClient)


# ---------- probe ----------------------------------------------------------

@pytest.mark.asyncio
async def test_probe_success(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "gitlab.com"
        assert "projects/ns%2Fproj" in req.url.raw_path.decode()
        assert req.headers["PRIVATE-TOKEN"] == "glpat_dummy"
        return httpx.Response(200, json={
            "id": 42, "path_with_namespace": "ns/proj",
            "default_branch": "main",
            "web_url": "https://gitlab.com/ns/proj",
            "visibility": "private",
        })
    _install_mock(monkeypatch, handler)
    meta = await gw.probe(repo_url="https://gitlab.com/ns/proj", pat="glpat_dummy")
    assert meta["default_branch"] == "main"
    assert meta["id"] == 42


@pytest.mark.asyncio
async def test_probe_bad_token_raises(monkeypatch):
    _install_mock(monkeypatch, lambda req: httpx.Response(401, text="unauthorized"))
    with pytest.raises(RepositoryAccessError):
        await gw.probe(repo_url="https://gitlab.com/ns/proj", pat="bad")


# ---------- commit_file ----------------------------------------------------

@pytest.mark.asyncio
async def test_commit_file_refuses_missing_branch(monkeypatch):
    def handler(req):
        # Branch existence probe → 404
        if "/branches/main" in req.url.path:
            return httpx.Response(404)
        raise AssertionError(f"unexpected call: {req.method} {req.url}")
    _install_mock(monkeypatch, handler)
    with pytest.raises(RepositoryAccessError) as ex:
        await gw.commit_file(
            repo_url="https://gitlab.com/ns/proj", pat="x",
            branch="main", path=".gitlab-ci.yml", content="hi",
            commit_message="c",
        )
    assert "does not exist" in str(ex.value)


@pytest.mark.asyncio
async def test_commit_file_creates_when_absent(monkeypatch):
    calls = {"post": 0}

    def handler(req):
        p = req.url.path
        if req.method == "GET" and "/branches/main" in p:
            return httpx.Response(200, json={
                "name": "main", "commit": {"id": "abc123"},
            })
        if req.method == "HEAD" and "/files/.gitlab-ci.yml" in p:
            return httpx.Response(404)
        if req.method == "POST" and "/files/.gitlab-ci.yml" in p:
            calls["post"] += 1
            return httpx.Response(201, json={"file_path": ".gitlab-ci.yml"})
        raise AssertionError(f"unexpected {req.method} {p}")
    _install_mock(monkeypatch, handler)
    out = await gw.commit_file(
        repo_url="https://gitlab.com/ns/proj", pat="x",
        branch="main", path=".gitlab-ci.yml", content="stages: [test]",
        commit_message="add pipeline",
    )
    assert calls["post"] == 1
    assert out["action"] == "add"
    assert out["commit_sha"] == "abc123"
    assert "commit/abc123" in out["commit_url"]


@pytest.mark.asyncio
async def test_commit_file_updates_when_present(monkeypatch):
    calls = {"put": 0}

    def handler(req):
        p = req.url.path
        if req.method == "GET" and "/branches/main" in p:
            return httpx.Response(200, json={
                "name": "main", "commit": {"id": "def456"},
            })
        if req.method == "HEAD" and "/files/.gitlab-ci.yml" in p:
            return httpx.Response(200)
        if req.method == "PUT" and "/files/.gitlab-ci.yml" in p:
            calls["put"] += 1
            return httpx.Response(200, json={"file_path": ".gitlab-ci.yml"})
        raise AssertionError(f"unexpected {req.method} {p}")
    _install_mock(monkeypatch, handler)
    out = await gw.commit_file(
        repo_url="https://gitlab.com/ns/proj", pat="x",
        branch="main", path=".gitlab-ci.yml", content="v2",
        commit_message="edit pipeline",
    )
    assert calls["put"] == 1
    assert out["action"] == "edit"
    assert out["commit_sha"] == "def456"


# ---------- open_merge_request --------------------------------------------

@pytest.mark.asyncio
async def test_open_merge_request_creates_branch_then_mr(monkeypatch):
    state = {"head_branch_created": False}

    def handler(req):
        raw = req.url.raw_path.decode()
        m = req.method
        # base branch check (URL-encoded: branches/main)
        if m == "GET" and raw.endswith("/branches/main"):
            return httpx.Response(200, json={
                "name": "main", "commit": {"id": "sha_main"},
            })
        # head branch check (URL-encoded slash: aipp%2Fpipeline)
        if m == "GET" and raw.endswith("/branches/aipp%2Fpipeline"):
            if not state["head_branch_created"]:
                return httpx.Response(404)
            return httpx.Response(200, json={
                "name": "aipp/pipeline", "commit": {"id": "sha_head"},
            })
        # create head branch
        if m == "POST" and raw.endswith("/repository/branches"):
            state["head_branch_created"] = True
            return httpx.Response(201, json={"name": "aipp/pipeline"})
        # file HEAD → not present (path includes ?ref=…)
        if m == "HEAD" and "/files/.gitlab-ci.yml" in raw:
            return httpx.Response(404)
        # file POST → created
        if m == "POST" and "/files/.gitlab-ci.yml" in raw:
            return httpx.Response(201, json={"file_path": ".gitlab-ci.yml"})
        # MR
        if m == "POST" and raw.endswith("/merge_requests"):
            return httpx.Response(201, json={
                "iid": 7,
                "web_url": "https://gitlab.com/ns/proj/-/merge_requests/7",
            })
        raise AssertionError(f"unexpected {m} {raw}")

    _install_mock(monkeypatch, handler)
    out = await gw.open_merge_request(
        repo_url="https://gitlab.com/ns/proj", pat="x",
        base_branch="main", head_branch="aipp/pipeline",
        path=".gitlab-ci.yml", content="stages: [test]",
        title="AIPP", body="test", commit_message="add pipeline",
    )
    assert out["action"] == "merge_request"
    assert out["pr_number"] == 7
    assert "/merge_requests/7" in out["pr_url"]
    assert state["head_branch_created"] is True
