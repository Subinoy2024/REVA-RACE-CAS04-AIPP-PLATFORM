"""Architecture Detection Agent."""

from __future__ import annotations

from backend.agents.base import BaseAgent
from backend.models.pipeline import ArchitectureProfile, TechnologyProfile
from backend.models.repository import RepositoryAnalysis

SYSTEM = """You are the AIPP Architecture Detection Agent.
Given a repository analysis and the detected technology profile, classify the
application architecture as one of: monolith, microservices, serverless, library,
unknown. Estimate the service count if microservices. Ground every claim in the
provided files — no speculation.
"""


class ArchitectureDetectionAgent(BaseAgent[ArchitectureProfile]):
    name = "architecture_detection_agent"
    response_model = ArchitectureProfile

    def __init__(self) -> None:
        super().__init__(system_prompt=SYSTEM)

    def _build_prompt(self, *, analysis: RepositoryAnalysis, tech: TechnologyProfile) -> str:
        return f"""Repository: {analysis.owner}/{analysis.name}
Detected language: {tech.language} / framework: {tech.framework}
Top-level paths: {analysis.top_paths}
Number of Dockerfiles: {len(analysis.dockerfiles)}
Number of K8s manifests: {len(analysis.kubernetes_files)}
Number of Helm charts: {len(analysis.helm_charts)}

Return JSON:
{{
  "style": "monolith|microservices|serverless|library|unknown",
  "service_count_estimate": 1,
  "entry_points": ["main.py", "cmd/api/main.go", ...],
  "databases": ["postgres", "redis", ...],
  "external_services": ["s3", "kafka", ...],
  "reasoning": "short explanation grounded in the files above"
}}
"""
