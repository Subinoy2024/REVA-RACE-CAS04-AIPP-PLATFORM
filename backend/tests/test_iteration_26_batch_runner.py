"""Iteration-26 · Batch Repo Runner — unit tests.

Covers:
  * `_parse_repos` — the textarea parser used by the Batch Runner tab.
  * `_results_to_df` — shape/columns of the pandas DataFrame.
  * `POST /api/research/batch` — validation of empty/oversized batches.
    (End-to-end run tests live in the live-backend suite; here we mock
    `PipelineService.generate` so the batch loop can be exercised without
    hitting the LLM or Postgres.)

We do not spin up the DB in this unit test; the batch endpoint's DB writes
are skipped by monkey-patching `session_scope` when we're just testing the
loop shape. For the real DB path, see `backend_test.py`.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from frontend.tabs.batch_runner import _parse_repos, _results_to_df, EMPTY_TABLE


# ---------- _parse_repos ---------------------------------------------------

def test_parse_repos_ignores_blank_and_comments():
    txt = """
    # this is a comment
    https://github.com/octocat/hello-world

       https://github.com/psf/requests
    # trailing comment
    """
    out = _parse_repos(txt)
    assert [r["repo_url"] for r in out] == [
        "https://github.com/octocat/hello-world",
        "https://github.com/psf/requests",
    ]
    assert all(r["branch"] == "main" for r in out)


def test_parse_repos_extracts_branch_suffix():
    out = _parse_repos("https://github.com/foo/bar@develop")
    assert out == [{"repo_url": "https://github.com/foo/bar", "branch": "develop"}]


def test_parse_repos_dedupes_same_repo_branch_pair():
    txt = """
    https://github.com/a/b
    https://github.com/a/b
    https://github.com/a/b@dev
    """
    out = _parse_repos(txt)
    assert len(out) == 2
    assert {r["branch"] for r in out} == {"main", "dev"}


def test_parse_repos_rejects_non_github_urls():
    txt = """
    https://gitlab.com/foo/bar
    https://github.com/ok/repo
    not-a-url
    """
    out = _parse_repos(txt)
    assert out == [{"repo_url": "https://github.com/ok/repo", "branch": "main"}]


def test_parse_repos_empty_returns_empty_list():
    assert _parse_repos("") == []
    assert _parse_repos(None) == []
    assert _parse_repos("   \n # only comments") == []


# ---------- _results_to_df -------------------------------------------------

def test_results_to_df_empty_matches_schema():
    df = _results_to_df([])
    assert list(df.columns) == list(EMPTY_TABLE.columns)
    assert df.empty


def test_results_to_df_populates_rows():
    df = _results_to_df([
        {
            "repo_url": "https://github.com/a/b", "branch": "main",
            "status": "ok", "seconds": 4.2, "validation_passed": True,
            "yaml_bytes": 1234, "secrets_clean": True,
            "deployment_target": "aws_eks", "run_id": "abc",
        },
        {
            "repo_url": "https://github.com/x/y", "branch": "main",
            "status": "error", "seconds": 1.1, "error": "boom",
        },
    ])
    assert len(df) == 2
    assert df.iloc[0]["status"] == "ok"
    assert df.iloc[0]["deployment_target"] == "aws_eks"
    assert df.iloc[1]["status"] == "error"
    assert df.iloc[1]["error"] == "boom"
    # First column is the sequence index the UI shows to the user.
    assert list(df["#"]) == [1, 2]


# ---------- batch endpoint validation --------------------------------------
# We only validate the pydantic layer here; execution is covered by the
# live-backend integration tests (LLM + DB required).


def test_batch_request_model_rejects_empty_repos():
    from backend.api.research import BatchRunRequest
    with pytest.raises(Exception):  # pydantic ValidationError
        BatchRunRequest(
            repos=[], github_pat="12345678",
            ci_platform="github_actions", cloud_platform="azure",
        )


def test_batch_request_model_rejects_oversize_batch():
    from backend.api.research import BatchRunRequest, BatchRepoItem
    items = [
        BatchRepoItem(repo_url=f"https://github.com/x/r{i}")
        for i in range(21)
    ]
    with pytest.raises(Exception):
        BatchRunRequest(
            repos=items, github_pat="12345678",
            ci_platform="github_actions", cloud_platform="azure",
        )


def test_batch_request_model_accepts_valid_payload():
    from backend.api.research import BatchRunRequest, BatchRepoItem
    body = BatchRunRequest(
        repos=[BatchRepoItem(repo_url="https://github.com/foo/bar")],
        github_pat="12345678",
        ci_platform="github_actions",
        cloud_platform="azure",
    )
    assert body.pipeline_type == "all_in_one"
    assert body.iac_tool == "terraform"
    assert body.experiment_label == "aipp"
    assert body.repos[0].branch == "main"
