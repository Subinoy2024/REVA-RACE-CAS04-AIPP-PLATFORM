"""LangGraph state definition."""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class AIPPState(TypedDict, total=False):
    # inputs
    repo_url: str
    github_pat: str
    branch: str
    ci_platform: str
    cloud_platform: str
    custom_requirement: str
    stream_id: Optional[str]
    pipeline_type: str
    agent_pool: Optional[str]
    # Opt-in Infra-as-Code selector. Default is "terraform" for ALL clouds
    # (AWS, Azure, GCP). Users can force "bicep" as an escape hatch, but it
    # only takes effect when cloud == azure; on any other cloud it is
    # ignored and Terraform is still emitted.
    iac_tool: str
    # Iteration-21: user-selected concrete deployment target (aws_eks,
    # azure_webapp, gcp_cloud_run, ...). "unspecified" means the planner
    # decides based on repo analysis.
    deployment_target: str

    # intermediate outputs
    analysis: dict
    tech: dict
    architecture: dict
    plan: dict
    environments: dict
    pipeline: dict
    validation: dict

    # final
    explanation: str
    error: Optional[str]

    # iteration-27: run-scoped UUID used as FK for `agent_traces` rows.
    # Generated up-front by PipelineService so every wrapped agent knows
    # which bucket to write its trace into.
    run_id: Optional[str]
