"""GitLab write helpers used by the Auto-Deploy flow.

Iteration-26 — GitLab parity with the GitHub/Azure DevOps writers.

Uses the GitLab v4 REST API. Authenticates with a Personal Access Token
(`PRIVATE-TOKEN` header) that needs at least `write_repository` scope
(`api` also works but is broader). Works with both:

  * SaaS  — https://gitlab.com/<group>/<subgroup>/<project>
  * Self-hosted — https://<host>/<group>/<project>

Design guarantees mirror the other writers:
  * NEVER auto-create the target branch on `commit_file`.
  * PR creation via `merge_requests` API — the base branch must exist.
  * Every failure raises `RepositoryAccessError` with the upstream status
    and (truncated) response body so users can debug PAT scopes.

Docs:
  Projects       https://docs.gitlab.com/ee/api/projects.html
  Repo files     https://docs.gitlab.com/ee/api/repository_files.html
  Branches       https://docs.gitlab.com/ee/api/branches.html
  Merge requests https://docs.gitlab.com/ee/api/merge_requests.html
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

from backend.core.exceptions import RepositoryAccessError


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------
@dataclass
class GitLabRepo:
    api_base: str    # https://gitlab.com/api/v4 (or self-hosted equivalent)
    web_base: str    # https://gitlab.com/<full/path>
    full_path: str   # `<group>/<subgroup?>/<project>` — used URL-encoded


def parse_gitlab_url(url: str) -> GitLabRepo:
    """Parse SaaS or self-hosted GitLab URL into API/project components.

    Accepts either bare or `.git`-suffixed URLs.
    """
    parsed = urlparse(str(url).strip())
    host = parsed.netloc
    if not host:
        raise RepositoryAccessError(f"Not a valid GitLab URL: {url}")
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if "/" not in path:
        raise RepositoryAccessError(
            f"Not a GitLab project URL (need group/project): {url}"
        )
    scheme = parsed.scheme or "https"
    api_base = f"{scheme}://{host}/api/v4"
    web_base = f"{scheme}://{host}/{path}"
    return GitLabRepo(api_base=api_base, web_base=web_base, full_path=path)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------
def _headers(pat: str) -> dict:
    return {
        "PRIVATE-TOKEN": pat,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _pid(repo: GitLabRepo) -> str:
    """Project identifier — URL-encoded namespace path per GitLab spec."""
    return quote(repo.full_path, safe="")


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
async def probe(*, repo_url: str, pat: str) -> dict:
    """Verify the PAT can read the project. Returns basic metadata."""
    r = parse_gitlab_url(repo_url)
    url = f"{r.api_base}/projects/{_pid(r)}"
    async with httpx.AsyncClient(timeout=20.0) as c:
        resp = await c.get(url, headers=_headers(pat))
    if resp.status_code >= 400:
        raise RepositoryAccessError(
            f"GitLab probe failed ({resp.status_code}): {resp.text[:200]}"
        )
    data = resp.json()
    return {
        "id": data.get("id"),
        "name": data.get("path_with_namespace") or data.get("name"),
        "default_branch": data.get("default_branch") or "main",
        "web_url": data.get("web_url"),
        "visibility": data.get("visibility"),
    }


async def _branch_exists(client: httpx.AsyncClient, r: GitLabRepo,
                         pat: str, branch: str) -> bool:
    url = f"{r.api_base}/projects/{_pid(r)}/repository/branches/{quote(branch, safe='')}"
    resp = await client.get(url, headers=_headers(pat))
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        return False
    raise RepositoryAccessError(
        f"Cannot check branch ({resp.status_code}): {resp.text[:200]}"
    )


async def _file_exists(client: httpx.AsyncClient, r: GitLabRepo,
                       pat: str, path: str, branch: str) -> bool:
    url = (
        f"{r.api_base}/projects/{_pid(r)}/repository/files/"
        f"{quote(path, safe='')}?ref={quote(branch, safe='')}"
    )
    # HEAD is honoured by GitLab and avoids downloading the base64 body.
    resp = await client.head(url, headers=_headers(pat))
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        return False
    raise RepositoryAccessError(
        f"Cannot check file ({resp.status_code}): {resp.text[:200]}"
    )


async def commit_file(
    *,
    repo_url: str,
    pat: str,
    branch: str,
    path: str,
    content: str,
    commit_message: str,
) -> dict:
    """Create or update a file on an existing branch.

    Refuses to auto-create the branch — parity with the GitHub / ADO
    writers. Returns commit SHA + a browsable URL.
    """
    r = parse_gitlab_url(repo_url)
    async with httpx.AsyncClient(timeout=30.0) as c:
        if not await _branch_exists(c, r, pat, branch):
            raise RepositoryAccessError(
                f"Branch '{branch}' does not exist on {r.full_path}. "
                f"Refusing to create it."
            )
        exists = await _file_exists(c, r, pat, path, branch)
        method = "PUT" if exists else "POST"
        action = "edit" if exists else "add"
        url = (
            f"{r.api_base}/projects/{_pid(r)}/repository/files/"
            f"{quote(path, safe='')}"
        )
        payload = {
            "branch": branch,
            "content": content,
            "commit_message": commit_message,
            "encoding": "text",
        }
        resp = await c.request(method, url, headers=_headers(pat), json=payload)
        if resp.status_code >= 400:
            raise RepositoryAccessError(
                f"GitLab commit failed ({resp.status_code}): {resp.text[:400]}"
            )
        data = resp.json() or {}
        # `commits/:sha` doesn't return in this response; fetch branch tip.
        tip_url = (
            f"{r.api_base}/projects/{_pid(r)}/repository/branches/"
            f"{quote(branch, safe='')}"
        )
        tip = await c.get(tip_url, headers=_headers(pat))
        commit_sha = None
        if tip.status_code == 200:
            commit_sha = ((tip.json() or {}).get("commit") or {}).get("id")
        commit_url = f"{r.web_base}/-/commit/{commit_sha}" if commit_sha else r.web_base
        return {
            "action": action,
            "branch": branch,
            "path": data.get("file_path", path),
            "commit_sha": commit_sha,
            "commit_url": commit_url,
        }


async def open_merge_request(
    *,
    repo_url: str,
    pat: str,
    base_branch: str,
    head_branch: str,
    path: str,
    content: str,
    title: str,
    body: str,
    commit_message: str,
) -> dict:
    """Create `head_branch` from `base_branch` if missing, commit, open MR."""
    r = parse_gitlab_url(repo_url)
    async with httpx.AsyncClient(timeout=30.0) as c:
        if not await _branch_exists(c, r, pat, base_branch):
            raise RepositoryAccessError(
                f"Base branch '{base_branch}' does not exist on {r.full_path}."
            )
        if not await _branch_exists(c, r, pat, head_branch):
            create_url = f"{r.api_base}/projects/{_pid(r)}/repository/branches"
            resp = await c.post(
                create_url, headers=_headers(pat),
                json={"branch": head_branch, "ref": base_branch},
            )
            if resp.status_code >= 400:
                raise RepositoryAccessError(
                    f"Cannot create branch ({resp.status_code}): "
                    f"{resp.text[:200]}"
                )

    commit_res = await commit_file(
        repo_url=repo_url, pat=pat, branch=head_branch,
        path=path, content=content, commit_message=commit_message,
    )

    async with httpx.AsyncClient(timeout=30.0) as c:
        mr_url = f"{r.api_base}/projects/{_pid(r)}/merge_requests"
        resp = await c.post(mr_url, headers=_headers(pat), json={
            "source_branch": head_branch,
            "target_branch": base_branch,
            "title": title,
            "description": body,
            "remove_source_branch": False,
        })
        if resp.status_code >= 400 and resp.status_code != 409:
            raise RepositoryAccessError(
                f"Cannot open MR ({resp.status_code}): {resp.text[:400]}"
            )
        pr_web: Optional[str] = None
        pr_id: Optional[int] = None
        if resp.status_code == 409:
            # Existing MR — link to the merge_requests list page.
            pr_web = f"{r.web_base}/-/merge_requests"
        else:
            data = resp.json() or {}
            pr_id = data.get("iid")
            pr_web = data.get("web_url") or (
                f"{r.web_base}/-/merge_requests/{pr_id}" if pr_id else r.web_base
            )

    return {
        "action": "merge_request",
        "base": base_branch,
        "head": head_branch,
        "path": path,
        "commit_sha": commit_res.get("commit_sha"),
        "commit_url": commit_res.get("commit_url"),
        "pr_url": pr_web,
        "pr_number": pr_id,
    }
