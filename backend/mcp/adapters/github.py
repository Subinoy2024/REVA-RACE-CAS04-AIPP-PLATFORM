"""GitHub MCP adapter — real API calls via PyGithub with a supplied PAT.

Never logs the PAT. Never stores it. It stays only in memory for the duration
of the request.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, List, Optional
from urllib.parse import urlparse

from backend.core.exceptions import RepositoryAccessError
from backend.core.logging import get_logger
from backend.mcp.adapters.base import BaseMCPAdapter

logger = get_logger(__name__)


@dataclass
class ParsedRepo:
    owner: str
    name: str


def parse_github_url(url: str) -> ParsedRepo:
    parsed = urlparse(str(url).strip())
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = re.split(r"[/]", path)
    if len(parts) < 2:
        raise RepositoryAccessError(f"Unable to parse GitHub URL: {url}")
    return ParsedRepo(owner=parts[0], name=parts[1])


class GitHubAdapter(BaseMCPAdapter):
    name = "github"

    def _register_tools(self) -> None:
        self._register("get_repository", self._get_repository)
        self._register("list_files", self._list_files)
        self._register("get_file_content", self._get_file_content)
        self._register("commit_file", self._commit_file)
        self._register("list_branches", self._list_branches)
        self._register("trigger_workflow_dispatch", self._trigger_workflow_dispatch)
        self._register("open_pull_request", self._open_pull_request)

    # PyGithub is fully synchronous; wrap in thread to keep the event loop free.
    def _client(self, pat: str):
        try:
            from github import Auth, Github  # PyGithub
        except ImportError as e:  # pragma: no cover
            raise RepositoryAccessError(f"PyGithub not installed: {e}")
        return Github(auth=Auth.Token(pat), per_page=100)

    async def _get_repository(self, *, url: str, pat: str, branch: str = "main") -> dict:
        parsed = parse_github_url(url)

        def _work() -> dict:
            gh = self._client(pat)
            try:
                repo = gh.get_repo(f"{parsed.owner}/{parsed.name}")
                return {
                    "owner": parsed.owner,
                    "name": parsed.name,
                    "default_branch": repo.default_branch,
                    "branch": branch or repo.default_branch,
                    "description": repo.description,
                    "private": repo.private,
                }
            except Exception as e:
                raise RepositoryAccessError(f"Cannot access {parsed.owner}/{parsed.name}: {e}")
            finally:
                gh.close()

        return await asyncio.to_thread(_work)

    async def _list_files(self, *, url: str, pat: str, branch: str, max_files: int = 400) -> List[dict]:
        parsed = parse_github_url(url)

        def _work() -> List[dict]:
            gh = self._client(pat)
            try:
                repo = gh.get_repo(f"{parsed.owner}/{parsed.name}")
                try:
                    tree = repo.get_git_tree(branch, recursive=True)
                except Exception:
                    tree = repo.get_git_tree(repo.default_branch, recursive=True)
                out = []
                for element in tree.tree[:max_files]:
                    if element.type != "blob":
                        continue
                    out.append({"path": element.path, "size": element.size or 0, "sha": element.sha})
                return out
            finally:
                gh.close()

        return await asyncio.to_thread(_work)

    async def _get_file_content(self, *, url: str, pat: str, path: str, branch: str, max_bytes: int = 20_000) -> Optional[str]:
        parsed = parse_github_url(url)

        def _work() -> Optional[str]:
            gh = self._client(pat)
            try:
                repo = gh.get_repo(f"{parsed.owner}/{parsed.name}")
                try:
                    f = repo.get_contents(path, ref=branch)
                except Exception:
                    f = repo.get_contents(path, ref=repo.default_branch)
                if isinstance(f, list):
                    return None
                if f.size and f.size > max_bytes:
                    return None
                try:
                    return f.decoded_content.decode("utf-8", errors="ignore")
                except Exception:
                    return None
            finally:
                gh.close()

        return await asyncio.to_thread(_work)


    async def _commit_file(
        self,
        *,
        url: str,
        pat: str,
        branch: str,
        path: str,
        content: str,
        message: str,
    ) -> dict:
        """Create or update a single file on the SPECIFIED branch.

        SAFETY: Never falls back to any other branch. If the branch does not
        exist, this raises so the caller can decide what to do — we never
        auto-create branches, and we never write to `main` unless the user
        explicitly picked `main` in the UI.
        """
        parsed = parse_github_url(url)
        if not branch or branch.strip() in {"", "*"}:
            raise RepositoryAccessError("commit_file requires an explicit target branch")

        def _work() -> dict:
            gh = self._client(pat)
            try:
                repo = gh.get_repo(f"{parsed.owner}/{parsed.name}")
                # Verify the branch exists — refuse silently to create it.
                try:
                    repo.get_branch(branch)
                except Exception as e:
                    raise RepositoryAccessError(
                        f"Target branch '{branch}' does not exist on "
                        f"{parsed.owner}/{parsed.name}. Refusing to create it."
                    )

                # Check if the file exists on that branch (update) or not (create).
                existing_sha = None
                try:
                    existing = repo.get_contents(path, ref=branch)
                    if isinstance(existing, list):
                        raise RepositoryAccessError(f"'{path}' is a directory, not a file")
                    existing_sha = existing.sha
                except Exception:
                    existing_sha = None

                if existing_sha:
                    result = repo.update_file(
                        path=path, message=message, content=content,
                        sha=existing_sha, branch=branch,
                    )
                    action = "updated"
                else:
                    result = repo.create_file(
                        path=path, message=message, content=content, branch=branch,
                    )
                    action = "created"

                commit = result["commit"] if isinstance(result, dict) else result
                return {
                    "action": action,
                    "branch": branch,
                    "path": path,
                    "commit_sha": commit.sha if hasattr(commit, "sha") else None,
                    "commit_url": commit.html_url if hasattr(commit, "html_url") else None,
                }
            finally:
                gh.close()

        return await asyncio.to_thread(_work)

    async def _list_branches(self, *, url: str, pat: str, max_branches: int = 100) -> List[str]:
        parsed = parse_github_url(url)

        def _work() -> List[str]:
            gh = self._client(pat)
            try:
                repo = gh.get_repo(f"{parsed.owner}/{parsed.name}")
                return [b.name for b in list(repo.get_branches())[:max_branches]]
            except GithubException as e:
                raise RepositoryAccessError(
                    f"Cannot list branches for {parsed.owner}/{parsed.name}: "
                    f"{getattr(e, 'status', '?')} {getattr(e, 'data', str(e))}"
                )
            finally:
                gh.close()

        return await asyncio.to_thread(_work)

    async def _trigger_workflow_dispatch(
        self,
        *,
        url: str,
        pat: str,
        workflow_file: str,
        branch: str,
        inputs: Optional[dict] = None,
    ) -> dict:
        """Trigger a `workflow_dispatch` event for a GitHub Actions workflow.

        `workflow_file` is the name only (e.g. `aipp-pipeline.yml`), not the
        full path. The `branch` param is BOTH the git ref to run against AND
        the branch the workflow file lives on.
        """
        parsed = parse_github_url(url)
        if not branch:
            raise RepositoryAccessError("trigger_workflow_dispatch requires an explicit branch")

        def _work() -> dict:
            gh = self._client(pat)
            try:
                repo = gh.get_repo(f"{parsed.owner}/{parsed.name}")
                wf = repo.get_workflow(workflow_file)
                dispatched = wf.create_dispatch(branch, inputs or {})
                return {
                    "dispatched": bool(dispatched),
                    "workflow": workflow_file,
                    "branch": branch,
                    "runs_url": f"https://github.com/{parsed.owner}/{parsed.name}/actions/workflows/{workflow_file}",
                }
            finally:
                gh.close()


    async def _open_pull_request(
        self,
        *,
        url: str,
        pat: str,
        base_branch: str,
        head_branch: str,
        path: str,
        content: str,
        title: str,
        body: str,
        commit_message: str,
    ) -> dict:
        """Create `head_branch` from `base_branch`, commit `path` on it,
        and open a PR into `base_branch`.

        Iteration-25 (Auto-Deploy — PR mode). Chosen over direct commit as
        the default because it puts a human review gate between AIPP and
        the deployment repository. Safe by construction.
        """
        parsed = parse_github_url(url)

        def _work() -> dict:
            gh = self._client(pat)
            try:
                repo = gh.get_repo(f"{parsed.owner}/{parsed.name}")
                # 1) Resolve base SHA
                base_ref = repo.get_branch(base_branch)
                base_sha = base_ref.commit.sha
                # 2) Create head branch if missing (idempotent)
                try:
                    repo.get_branch(head_branch)
                except Exception:
                    repo.create_git_ref(f"refs/heads/{head_branch}", base_sha)
                # 3) Create or update the file on the head branch
                existing_sha = None
                try:
                    existing = repo.get_contents(path, ref=head_branch)
                    if isinstance(existing, list):
                        raise RepositoryAccessError(f"'{path}' is a directory, not a file")
                    existing_sha = existing.sha
                except Exception:
                    existing_sha = None
                if existing_sha:
                    result = repo.update_file(
                        path=path, message=commit_message, content=content,
                        sha=existing_sha, branch=head_branch,
                    )
                else:
                    result = repo.create_file(
                        path=path, message=commit_message, content=content,
                        branch=head_branch,
                    )
                commit = result["commit"] if isinstance(result, dict) else result
                # 4) Open the PR (or reuse if one already exists)
                try:
                    pr = repo.create_pull(
                        title=title, body=body,
                        base=base_branch, head=head_branch,
                        maintainer_can_modify=True,
                    )
                    pr_url = pr.html_url
                    pr_number = pr.number
                except Exception as e:
                    # A PR might already be open — surface a helpful URL.
                    pr_url = f"https://github.com/{parsed.owner}/{parsed.name}/pulls"
                    pr_number = None
                    logger.info("aipp.github.pr: reuse or create failed: %s", e)
                return {
                    "action": "pull_request",
                    "base": base_branch,
                    "head": head_branch,
                    "path": path,
                    "commit_sha": commit.sha if hasattr(commit, "sha") else None,
                    "commit_url": commit.html_url if hasattr(commit, "html_url") else None,
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                }
            finally:
                gh.close()

        return await asyncio.to_thread(_work)

        return await asyncio.to_thread(_work)