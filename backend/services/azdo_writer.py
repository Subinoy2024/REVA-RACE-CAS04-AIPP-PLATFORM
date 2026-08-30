"""Azure DevOps write helpers used by the Auto-Deploy flow.

Kept separate from `adapters/azure_devops.py` so the MCP guard boundary
stays clear: the MCP adapter exposes read-only tools; anything that
mutates the deployment repo lives here and is called by the deployment
service under explicit user consent.

Docs referenced (all v7.1):
  Pushes API           https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pushes/create
  Refs API             https://learn.microsoft.com/en-us/rest/api/azure/devops/git/refs/list
  Pull Requests API    https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-requests/create
  Repositories API     https://learn.microsoft.com/en-us/rest/api/azure/devops/git/repositories/get-repository
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, quote

import httpx

from backend.core.exceptions import RepositoryAccessError


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------
@dataclass
class AzDoRepo:
    org_url: str          # https://dev.azure.com/<org>
    project: str
    repo: str


def parse_azdo_url(url: str) -> AzDoRepo:
    """Accept both classic and modern Azure DevOps repo URLs.

    Examples:
      https://dev.azure.com/myorg/MyProject/_git/MyRepo
      https://myorg.visualstudio.com/MyProject/_git/MyRepo
    """
    parsed = urlparse(str(url).strip())
    host = parsed.netloc
    path = parsed.path.strip("/")
    parts = re.split(r"[/]", path)
    if "_git" not in parts:
        raise RepositoryAccessError(f"Not an Azure DevOps repo URL: {url}")
    idx = parts.index("_git")
    if idx < 1 or idx + 1 >= len(parts):
        raise RepositoryAccessError(f"Unable to parse Azure DevOps URL: {url}")
    project = parts[idx - 1]
    repo = parts[idx + 1]
    if host.endswith("visualstudio.com"):
        org = host.split(".")[0]
        org_url = f"https://dev.azure.com/{org}"
    else:
        # dev.azure.com/<org>/... — the org is the first path segment
        if idx - 1 < 1:
            raise RepositoryAccessError(f"Missing org in Azure DevOps URL: {url}")
        org = parts[0]
        org_url = f"https://{host}/{org}"
    return AzDoRepo(org_url=org_url, project=project, repo=repo)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------
def _headers(pat: str) -> dict:
    token = base64.b64encode(f":{pat}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
async def probe(*, repo_url: str, pat: str) -> dict:
    """Verify the PAT can read the repository. Returns basic metadata."""
    r = parse_azdo_url(repo_url)
    url = f"{r.org_url}/{quote(r.project)}/_apis/git/repositories/{quote(r.repo)}?api-version=7.1"
    async with httpx.AsyncClient(timeout=20.0) as c:
        resp = await c.get(url, headers=_headers(pat))
    if resp.status_code >= 400:
        raise RepositoryAccessError(
            f"Azure DevOps probe failed ({resp.status_code}): {resp.text[:200]}"
        )
    data = resp.json()
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "default_branch": (data.get("defaultBranch") or "").replace("refs/heads/", ""),
        "size": data.get("size"),
        "web_url": data.get("webUrl"),
    }


async def _get_ref_object_id(client: httpx.AsyncClient, r: AzDoRepo, pat: str, branch: str) -> Optional[str]:
    url = (
        f"{r.org_url}/{quote(r.project)}/_apis/git/repositories/"
        f"{quote(r.repo)}/refs?filter=heads/{quote(branch)}&api-version=7.1"
    )
    resp = await client.get(url, headers=_headers(pat))
    if resp.status_code >= 400:
        raise RepositoryAccessError(
            f"Cannot list refs ({resp.status_code}): {resp.text[:200]}"
        )
    items = resp.json().get("value") or []
    for it in items:
        if it.get("name") == f"refs/heads/{branch}":
            return it.get("objectId")
    return None


async def commit_file(
    *,
    repo_url: str,
    pat: str,
    branch: str,
    path: str,
    content: str,
    commit_message: str,
) -> dict:
    """Commit or update a file on an existing branch.

    Refuses to auto-create the branch — parity with the GitHub adapter.
    Returns commit SHA + a browsable URL.
    """
    r = parse_azdo_url(repo_url)
    async with httpx.AsyncClient(timeout=30.0) as c:
        old_object_id = await _get_ref_object_id(c, r, pat, branch)
        if not old_object_id:
            raise RepositoryAccessError(
                f"Branch '{branch}' does not exist on {r.project}/{r.repo}. "
                f"Refusing to create it."
            )
        # Decide edit vs add — Azure DevOps Pushes API requires the right
        # `changeType`. We probe the file at the branch tip.
        change_type = "edit"
        probe_url = (
            f"{r.org_url}/{quote(r.project)}/_apis/git/repositories/"
            f"{quote(r.repo)}/items?path={quote(path)}&versionDescriptor.version={quote(branch)}"
            f"&api-version=7.1&includeContent=false"
        )
        probe_resp = await c.get(probe_url, headers=_headers(pat))
        if probe_resp.status_code == 404:
            change_type = "add"
        elif probe_resp.status_code >= 400 and probe_resp.status_code != 200:
            raise RepositoryAccessError(
                f"Cannot probe file existence ({probe_resp.status_code}): "
                f"{probe_resp.text[:200]}"
            )

        payload = {
            "refUpdates": [{"name": f"refs/heads/{branch}", "oldObjectId": old_object_id}],
            "commits": [{
                "comment": commit_message,
                "changes": [{
                    "changeType": change_type,
                    "item": {"path": path if path.startswith("/") else f"/{path}"},
                    "newContent": {"content": content, "contentType": "rawtext"},
                }],
            }],
        }
        push_url = (
            f"{r.org_url}/{quote(r.project)}/_apis/git/repositories/"
            f"{quote(r.repo)}/pushes?api-version=7.1"
        )
        resp = await c.post(push_url, headers=_headers(pat), json=payload)
        if resp.status_code >= 400:
            raise RepositoryAccessError(
                f"Azure DevOps push failed ({resp.status_code}): {resp.text[:400]}"
            )
        push = resp.json()
        commit = (push.get("commits") or [{}])[0]
        return {
            "action": change_type,
            "branch": branch,
            "path": path,
            "commit_sha": commit.get("commitId"),
            "commit_url": commit.get("remoteUrl") or push.get("_links", {}).get("web", {}).get("href"),
        }


async def open_pull_request(
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
    """Create `head_branch` from `base_branch` if missing, commit file, open PR."""
    r = parse_azdo_url(repo_url)
    async with httpx.AsyncClient(timeout=30.0) as c:
        base_object_id = await _get_ref_object_id(c, r, pat, base_branch)
        if not base_object_id:
            raise RepositoryAccessError(
                f"Base branch '{base_branch}' does not exist on "
                f"{r.project}/{r.repo}."
            )
        head_object_id = await _get_ref_object_id(c, r, pat, head_branch)
        if not head_object_id:
            # Create head branch from base_object_id via refs POST
            create_url = (
                f"{r.org_url}/{quote(r.project)}/_apis/git/repositories/"
                f"{quote(r.repo)}/refs?api-version=7.1"
            )
            create_payload = [{
                "name": f"refs/heads/{head_branch}",
                "oldObjectId": "0000000000000000000000000000000000000000",
                "newObjectId": base_object_id,
            }]
            resp = await c.post(create_url, headers=_headers(pat), json=create_payload)
            if resp.status_code >= 400:
                raise RepositoryAccessError(
                    f"Cannot create branch ({resp.status_code}): {resp.text[:200]}"
                )
            head_object_id = base_object_id

    # File commit
    commit_res = await commit_file(
        repo_url=repo_url, pat=pat, branch=head_branch,
        path=path, content=content, commit_message=commit_message,
    )

    async with httpx.AsyncClient(timeout=30.0) as c:
        pr_url = (
            f"{r.org_url}/{quote(r.project)}/_apis/git/repositories/"
            f"{quote(r.repo)}/pullrequests?api-version=7.1"
        )
        pr_payload = {
            "sourceRefName": f"refs/heads/{head_branch}",
            "targetRefName": f"refs/heads/{base_branch}",
            "title": title,
            "description": body,
        }
        resp = await c.post(pr_url, headers=_headers(pat), json=pr_payload)
        if resp.status_code >= 400 and resp.status_code != 409:
            raise RepositoryAccessError(
                f"Cannot open PR ({resp.status_code}): {resp.text[:400]}"
            )
        if resp.status_code == 409:
            pr_web = f"{r.org_url}/{quote(r.project)}/_git/{quote(r.repo)}/pullrequests"
            pr_id = None
        else:
            data = resp.json()
            pr_id = data.get("pullRequestId")
            pr_web = (
                f"{r.org_url}/{quote(r.project)}/_git/{quote(r.repo)}"
                f"/pullrequest/{pr_id}" if pr_id else None
            )

    return {
        "action": "pull_request",
        "base": base_branch,
        "head": head_branch,
        "path": path,
        "commit_sha": commit_res.get("commit_sha"),
        "commit_url": commit_res.get("commit_url"),
        "pr_url": pr_web,
        "pr_number": pr_id,
    }
