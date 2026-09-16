"""Deployment-target CRUD + Auto-Deploy orchestrator.

Iteration-25.  User-controlled auto-deploy flow:

    1. User onboards a deployment target (GitHub or Azure DevOps) with a
       write-scoped PAT. Token is Fernet-encrypted (`crypto_service`).
    2. From the Pipeline Generator, the user picks a saved target,
       chooses a mode (`pr` recommended | `commit`), and confirms.
    3. This service executes the write via the appropriate adapter and
       records the attempt in the `deployments` table.

Design guarantees:
    * We never write to the analyzed source repo — only to the target repo
      the user explicitly onboarded.
    * We never auto-create branches on `commit` mode.
    * We record every attempt (success or failure) to `deployments` for
      audit / thesis eval.
    * Every raw PAT stays in memory only for the duration of the request;
      we decrypt on demand and drop the reference.
"""

from __future__ import annotations

import hashlib
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from backend.core.exceptions import RepositoryAccessError
from backend.core.logging import get_logger
from backend.database.connection import session_scope
from backend.database.models import Deployment, DeploymentTarget
from backend.mcp.adapters.github import GitHubAdapter
from backend.services import azdo_writer, gitlab_writer
from backend.services.crypto_service import decrypt, encrypt
from backend.services.secret_scanner import scan_report as _secret_scan

logger = get_logger(__name__)

# Per-platform file path convention — matches api/deployment.py
CI_PATH = {
    "github_actions": ".github/workflows/aipp-pipeline.yml",
    "azure_devops":   "azure-pipelines.yml",
    "gitlab_ci":      ".gitlab-ci.yml",
    "harness":        ".harness/pipeline.yml",
    "tekton":         ".tekton/pipeline.yaml",
}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def _redact(t: DeploymentTarget) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "platform": t.platform,
        "repo_url": t.repo_url,
        "default_branch": t.default_branch,
        "extra": t.extra_json or {},
        "is_active": t.is_active,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


async def create_target(
    *,
    owner_email: str,
    name: str,
    platform: str,
    repo_url: str,
    default_branch: str,
    token_plain: str,
    extra: Optional[dict] = None,
) -> dict:
    if platform not in ("github_actions", "azure_devops", "gitlab_ci"):
        raise ValueError(f"Unsupported platform: {platform}")
    if not token_plain or len(token_plain) < 8:
        raise ValueError("Access token is required (min 8 chars)")

    # iter-26.7 · repo_url is now optional at onboard time — the deployment
    # repo is picked per-push on the Pipeline Generator page. Empty string
    # is stored as "" (schema is NOT NULL for backwards-compat).
    repo_url_clean = (repo_url or "").strip()

    async with session_scope() as sess:
        row = DeploymentTarget(
            owner_email=owner_email,
            name=name.strip(),
            platform=platform,
            repo_url=repo_url_clean,
            default_branch=(default_branch or "main").strip(),
            token_encrypted=encrypt(token_plain),
            extra_json=extra or {},
            is_active=True,
        )
        sess.add(row)
        await sess.flush()
        logger.info("aipp.deploy.target.created owner=%s platform=%s repo=%s",
                    owner_email, platform, repo_url_clean or "(picked per push)")
        return _redact(row)


async def list_targets(owner_email: str) -> list[dict]:
    async with session_scope() as sess:
        rows = (await sess.execute(
            select(DeploymentTarget)
            .where(DeploymentTarget.owner_email == owner_email)
            .order_by(DeploymentTarget.created_at.desc())
        )).scalars().all()
        return [_redact(r) for r in rows]


async def delete_target(*, owner_email: str, target_id: UUID) -> bool:
    async with session_scope() as sess:
        row = (await sess.execute(select(DeploymentTarget)
                                  .where(DeploymentTarget.id == target_id))).scalar_one_or_none()
        if row is None or row.owner_email != owner_email:
            return False
        await sess.delete(row)
        return True


async def _load_target(owner_email: str, target_id: UUID) -> DeploymentTarget:
    async with session_scope() as sess:
        row = (await sess.execute(
            select(DeploymentTarget).where(DeploymentTarget.id == target_id)
        )).scalar_one_or_none()
        if row is None or row.owner_email != owner_email:
            raise RepositoryAccessError("Unknown or unauthorised deployment target")
        if not row.is_active:
            raise RepositoryAccessError("Deployment target is disabled")
        # Detach for use outside the session
        sess.expunge(row)
        return row


async def test_target(*, owner_email: str, target_id: UUID) -> dict:
    """Probe the target repo — does the PAT work? Does the branch exist?"""
    tgt = await _load_target(owner_email, target_id)
    token = decrypt(tgt.token_encrypted)
    if tgt.platform == "github_actions":
        adapter = GitHubAdapter(); adapter._register_tools()
        meta = await adapter.call("get_repository", url=tgt.repo_url,
                                   pat=token, branch=tgt.default_branch)
        return {"ok": True, "platform": "github_actions", **meta}
    if tgt.platform == "azure_devops":
        meta = await azdo_writer.probe(repo_url=tgt.repo_url, pat=token)
        return {"ok": True, "platform": "azure_devops", **meta}
    if tgt.platform == "gitlab_ci":
        meta = await gitlab_writer.probe(repo_url=tgt.repo_url, pat=token)
        return {"ok": True, "platform": "gitlab_ci", **meta}
    raise RepositoryAccessError(f"Unknown platform: {tgt.platform}")


# ---------------------------------------------------------------------------
# Auto-deploy
# ---------------------------------------------------------------------------
def _sanitize_branch(name: str) -> str:
    keep = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/-_."
    return "".join(c for c in name if c in keep)[:120]


async def deploy(
    *,
    owner_email: str,
    target_id: UUID,
    ci_platform: str,
    yaml_content: str,
    mode: str = "pr",
    branch: Optional[str] = None,
    repo_url_override: Optional[str] = None,
    commit_message: Optional[str] = None,
) -> dict:
    """Push the YAML to the onboarded target.

    - `mode="pr"` → create a branch + open a PR (safest, recommended).
    - `mode="commit"` → direct commit to `branch` (requires existing branch).
    - `repo_url_override` (iter-26.7) — pick the deployment repo at push
      time. Required when the onboarded target has no saved `repo_url`.
    """
    if ci_platform not in CI_PATH:
        raise RepositoryAccessError(f"Unknown ci_platform: {ci_platform}")
    if mode not in ("pr", "commit"):
        raise RepositoryAccessError(f"Unknown mode: {mode}")
    if not yaml_content or len(yaml_content) < 20:
        raise RepositoryAccessError("YAML content is empty or too short")

    # Hard-fail if the YAML has embedded secrets — parity with api/deployment.py
    scan = _secret_scan(yaml_content)
    if scan["blocked"]:
        raise RepositoryAccessError(
            "Refusing to deploy — YAML contains suspected secrets. "
            "Rotate and regenerate."
        )

    tgt = await _load_target(owner_email, target_id)
    token = decrypt(tgt.token_encrypted)
    # iter-26.7 · resolve the effective repo_url — user's push-time override
    # wins over the target's saved default. At least one must be present.
    effective_repo_url = (repo_url_override or "").strip() or (tgt.repo_url or "").strip()
    if not effective_repo_url:
        raise RepositoryAccessError(
            "No deployment repo URL. Provide `repo_url` in the deploy call, "
            "or set a default on the Integrations target."
        )
    # Temporarily mutate the in-memory target so the branch-specific paths
    # below (which read `tgt.repo_url`) all see the same effective URL.
    tgt.repo_url = effective_repo_url

    branch = _sanitize_branch(branch or tgt.default_branch or "main")
    path = CI_PATH[ci_platform]
    commit_message = commit_message or "chore(aipp): update CI/CD pipeline generated by AIPP"

    dep = Deployment(
        target_id=tgt.id, owner_email=owner_email,
        platform=tgt.platform, repo_url=effective_repo_url,
        branch=branch, ci_platform=ci_platform, mode=mode,
        status="pending",
        yaml_sha256=hashlib.sha256(yaml_content.encode("utf-8")).hexdigest(),
    )
    async with session_scope() as sess:
        sess.add(dep); await sess.flush(); dep_id = dep.id

    try:
        if tgt.platform == "github_actions":
            adapter = GitHubAdapter(); adapter._register_tools()
            if mode == "pr":
                head = f"aipp/pipeline-{dep_id.hex[:8]}"
                result = await adapter.call(
                    "open_pull_request",
                    url=tgt.repo_url, pat=token,
                    base_branch=branch, head_branch=head,
                    path=path, content=yaml_content,
                    title="chore(aipp): AIPP-generated CI/CD pipeline",
                    body=(
                        "This pull request was opened by **AIPP** "
                        "(Automated Intelligent Pipeline Platform) at the user's request.\n\n"
                        f"* Target CI platform: `{ci_platform}`\n"
                        f"* Base branch: `{branch}`\n"
                        f"* Content SHA-256: `{dep.yaml_sha256}`\n"
                    ),
                    commit_message=commit_message,
                )
                ref_url = result.get("pr_url") or result.get("commit_url")
            else:
                result = await adapter.call(
                    "commit_file",
                    url=tgt.repo_url, pat=token,
                    branch=branch, path=path, content=yaml_content,
                    message=commit_message,
                )
                ref_url = result.get("commit_url")

        elif tgt.platform == "azure_devops":
            if mode == "pr":
                head = f"aipp/pipeline-{dep_id.hex[:8]}"
                result = await azdo_writer.open_pull_request(
                    repo_url=tgt.repo_url, pat=token,
                    base_branch=branch, head_branch=head,
                    path=path, content=yaml_content,
                    title="chore(aipp): AIPP-generated CI/CD pipeline",
                    body=(
                        f"AIPP-generated pipeline for `{ci_platform}`. "
                        f"Base: `{branch}`. Content SHA-256: `{dep.yaml_sha256}`."
                    ),
                    commit_message=commit_message,
                )
                ref_url = result.get("pr_url") or result.get("commit_url")
            else:
                result = await azdo_writer.commit_file(
                    repo_url=tgt.repo_url, pat=token,
                    branch=branch, path=path, content=yaml_content,
                    commit_message=commit_message,
                )
                ref_url = result.get("commit_url")
        elif tgt.platform == "gitlab_ci":
            if mode == "pr":
                head = f"aipp/pipeline-{dep_id.hex[:8]}"
                result = await gitlab_writer.open_merge_request(
                    repo_url=tgt.repo_url, pat=token,
                    base_branch=branch, head_branch=head,
                    path=path, content=yaml_content,
                    title="chore(aipp): AIPP-generated CI/CD pipeline",
                    body=(
                        f"AIPP-generated pipeline for `{ci_platform}`. "
                        f"Base: `{branch}`. Content SHA-256: `{dep.yaml_sha256}`."
                    ),
                    commit_message=commit_message,
                )
                ref_url = result.get("pr_url") or result.get("commit_url")
            else:
                result = await gitlab_writer.commit_file(
                    repo_url=tgt.repo_url, pat=token,
                    branch=branch, path=path, content=yaml_content,
                    commit_message=commit_message,
                )
                ref_url = result.get("commit_url")
        else:
            raise RepositoryAccessError(f"Unknown platform: {tgt.platform}")

        async with session_scope() as sess:
            row = (await sess.execute(select(Deployment).where(Deployment.id == dep_id))).scalar_one()
            row.status = "success"
            row.commit_sha = result.get("commit_sha")
            row.ref_url = ref_url
        return {"ok": True, "deployment_id": str(dep_id), **result}

    except Exception as e:
        async with session_scope() as sess:
            row = (await sess.execute(select(Deployment).where(Deployment.id == dep_id))).scalar_one()
            row.status = "failed"
            row.error = str(e)[:2000]
        logger.exception("aipp.deploy.failed target=%s: %s", tgt.id, e)
        raise


async def list_deployments(owner_email: str, limit: int = 50) -> list[dict]:
    async with session_scope() as sess:
        rows = (await sess.execute(
            select(Deployment)
            .where(Deployment.owner_email == owner_email)
            .order_by(Deployment.created_at.desc())
            .limit(limit)
        )).scalars().all()
        return [{
            "id": str(r.id),
            "target_id": str(r.target_id),
            "platform": r.platform,
            "ci_platform": r.ci_platform,
            "repo_url": r.repo_url,
            "branch": r.branch,
            "mode": r.mode,
            "status": r.status,
            "commit_sha": r.commit_sha,
            "ref_url": r.ref_url,
            "error": r.error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows]
