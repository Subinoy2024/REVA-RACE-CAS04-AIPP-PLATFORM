"""Pydantic schema for a repository submitted by the user."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class RepositoryRequest(BaseModel):
    repo_url: HttpUrl = Field(..., description="Full HTTPS URL of the GitHub repository")
    github_pat: str = Field(..., min_length=8, description="Read-only GitHub Personal Access Token")
    branch: str = Field("main", description="Branch to analyse")


class DetectedFile(BaseModel):
    path: str
    size: int = 0
    kind: str = "unknown"          # e.g. dockerfile, k8s_manifest, helm_chart, ci_workflow, source


class RepositoryAnalysis(BaseModel):
    """Structured output of the Repository Analysis Agent."""

    owner: str
    name: str
    branch: str
    default_branch: Optional[str] = None
    file_count: int = 0
    top_paths: List[str] = Field(default_factory=list)
    dependency_files: List[DetectedFile] = Field(default_factory=list)
    dockerfiles: List[DetectedFile] = Field(default_factory=list)
    kubernetes_files: List[DetectedFile] = Field(default_factory=list)
    helm_charts: List[DetectedFile] = Field(default_factory=list)
    existing_pipelines: List[DetectedFile] = Field(default_factory=list)
    infra_files: List[DetectedFile] = Field(default_factory=list)
    readme_snippet: Optional[str] = None
    notes: List[str] = Field(default_factory=list)
