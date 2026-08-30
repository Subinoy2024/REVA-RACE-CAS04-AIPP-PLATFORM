"""Repository Analysis Agent — reads the repo via GitHub MCP and produces a
structured RepositoryAnalysis. Uses heuristics first (deterministic, cheap)
then optionally passes a summary through the LLM for a natural-language note.
"""

from __future__ import annotations

from typing import Iterable, List

from backend.core.logging import get_logger
from backend.core.security import sanitize_repository_snippet
from backend.mcp.client import MCPClient
from backend.models.repository import DetectedFile, RepositoryAnalysis, RepositoryRequest

logger = get_logger(__name__)


DEPENDENCY_FILES = {
    "package.json", "yarn.lock", "package-lock.json", "pnpm-lock.yaml",
    "requirements.txt", "pyproject.toml", "poetry.lock", "pipfile", "pipfile.lock",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "go.mod", "go.sum", "cargo.toml", "cargo.lock",
    "gemfile", "gemfile.lock", "composer.json", "composer.lock",
    "*.csproj", "*.sln",
}
INFRA_HINTS = {
    "terraform": (".tf", ".tf.json"),
    "pulumi": ("pulumi.yaml", "pulumi.yml"),
    "cloudformation": ("cloudformation.yaml", "cloudformation.yml", "template.yaml"),
    "ansible": ("ansible.cfg",),
}
PIPELINE_HINTS = {
    ".github/workflows/": "github_actions",
    "azure-pipelines": "azure_devops",
    ".gitlab-ci": "gitlab_ci",
    ".harness/": "harness",
    "tekton": "tekton",
}


def _match(path: str, needle: str) -> bool:
    return needle in path.lower()


class RepositoryAnalysisAgent:
    name = "repository_analysis_agent"

    def __init__(self, mcp: MCPClient) -> None:
        self.mcp = mcp

    async def run(self, req: RepositoryRequest) -> RepositoryAnalysis:
        repo_meta = await self.mcp.call(
            "github", "get_repository", url=str(req.repo_url), pat=req.github_pat, branch=req.branch
        )
        files_raw = await self.mcp.call(
            "github", "list_files", url=str(req.repo_url), pat=req.github_pat, branch=req.branch
        )

        dep, dockers, k8s, helm, pipes, infra = [], [], [], [], [], []
        for f in files_raw:
            path = f["path"]
            lower = path.lower()
            base = lower.rsplit("/", 1)[-1]
            if base in DEPENDENCY_FILES or any(base == p or (p.startswith("*") and base.endswith(p[1:])) for p in DEPENDENCY_FILES):
                dep.append(DetectedFile(path=path, size=f.get("size", 0), kind="dependency"))
            if base == "dockerfile" or base.startswith("dockerfile."):
                dockers.append(DetectedFile(path=path, size=f.get("size", 0), kind="dockerfile"))
            if "kustomization" in base or lower.endswith((".yaml", ".yml")) and any(k in lower for k in ("k8s/", "kubernetes/", "manifests/", "kustomize/")):
                k8s.append(DetectedFile(path=path, size=f.get("size", 0), kind="k8s_manifest"))
            if base == "chart.yaml" or "/templates/" in lower:
                helm.append(DetectedFile(path=path, size=f.get("size", 0), kind="helm_chart"))
            for hint, kind in PIPELINE_HINTS.items():
                if hint in lower:
                    pipes.append(DetectedFile(path=path, size=f.get("size", 0), kind=kind))
                    break
            for iac, exts in INFRA_HINTS.items():
                if any(_match(lower, e) for e in exts):
                    infra.append(DetectedFile(path=path, size=f.get("size", 0), kind=iac))
                    break

        # readme snippet (sanitized)
        readme = None
        for f in files_raw:
            if f["path"].lower() in ("readme.md", "readme.rst", "readme.txt"):
                content = await self.mcp.call(
                    "github", "get_file_content",
                    url=str(req.repo_url), pat=req.github_pat, path=f["path"], branch=req.branch,
                    max_bytes=6000,
                )
                if content:
                    readme = sanitize_repository_snippet(content, max_chars=3000)
                break

        analysis = RepositoryAnalysis(
            owner=repo_meta["owner"],
            name=repo_meta["name"],
            branch=repo_meta.get("branch", req.branch),
            default_branch=repo_meta.get("default_branch"),
            file_count=len(files_raw),
            top_paths=_top_paths(files_raw),
            dependency_files=dep,
            dockerfiles=dockers,
            kubernetes_files=k8s,
            helm_charts=helm,
            existing_pipelines=pipes,
            infra_files=infra,
            readme_snippet=readme,
            notes=[
                f"Total files scanned: {len(files_raw)}",
                f"Container-ready: {'yes' if dockers else 'no'}",
                f"Kubernetes/Helm: {'yes' if (k8s or helm) else 'no'}",
                f"IaC detected: {sorted({f.kind for f in infra}) or 'none'}",
                f"Existing CI/CD: {sorted({f.kind for f in pipes}) or 'none'}",
            ],
        )
        return analysis


def _top_paths(files: Iterable[dict], depth: int = 1, limit: int = 15) -> List[str]:
    seen: dict[str, int] = {}
    for f in files:
        p = f["path"].split("/")
        key = "/".join(p[:depth]) if len(p) > 1 else p[0]
        seen[key] = seen.get(key, 0) + 1
    return [k for k, _ in sorted(seen.items(), key=lambda x: -x[1])[:limit]]
