"""Pydantic schemas for pipeline planning + generation."""

from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class CIPlatform(str, Enum):
    azure_devops = "azure_devops"
    github_actions = "github_actions"
    gitlab_ci = "gitlab_ci"
    harness = "harness"
    tekton = "tekton"


class CloudPlatform(str, Enum):
    azure = "azure"
    aws = "aws"
    gcp = "gcp"


class DeploymentTarget(str, Enum):
    """Concrete deployment surface inside the chosen cloud.

    Added in iteration-21 so the user can tell AIPP *exactly* where the app
    should land — otherwise the LLM has to guess and sometimes wrong.

    Design decision:
      - Not every combination is meaningful — Bicep can't deploy to GKE.
      - The generators / MCP adapters validate compatibility at runtime;
        the UI filters by selected cloud so users can only pick sensible
        options.
      - `unspecified` is the safe fallback — planner agent then decides
        based on repo analysis (agentic default).
    """
    unspecified = "unspecified"

    # AWS
    aws_eks = "aws_eks"
    aws_ecs = "aws_ecs"
    aws_lambda = "aws_lambda"
    aws_app_runner = "aws_app_runner"
    aws_ec2 = "aws_ec2"
    aws_asg = "aws_asg"

    # Azure
    azure_aks = "azure_aks"
    azure_webapp = "azure_webapp"
    azure_container_apps = "azure_container_apps"
    azure_functions = "azure_functions"
    azure_vm = "azure_vm"
    azure_vmss = "azure_vmss"

    # GCP
    gcp_gke = "gcp_gke"
    gcp_cloud_run = "gcp_cloud_run"
    gcp_cloud_functions = "gcp_cloud_functions"
    gcp_app_engine = "gcp_app_engine"
    gcp_gce = "gcp_gce"
    gcp_mig = "gcp_mig"


# Which deployment targets are valid for each cloud. UI uses this to filter
# the dropdown; backend uses it to reject nonsensical combinations.
CLOUD_TARGETS: dict[str, list[str]] = {
    "aws":   ["aws_eks", "aws_ecs", "aws_lambda", "aws_app_runner", "aws_ec2", "aws_asg"],
    "azure": ["azure_aks", "azure_webapp", "azure_container_apps", "azure_functions",
              "azure_vm", "azure_vmss"],
    "gcp":   ["gcp_gke", "gcp_cloud_run", "gcp_cloud_functions", "gcp_app_engine",
              "gcp_gce", "gcp_mig"],
}


# Human-readable label + one-line description used by the UI hint.
TARGET_LABELS: dict[str, str] = {
    "unspecified":          "Let AIPP decide (recommended)",
    "aws_eks":              "AWS EKS — managed Kubernetes",
    "aws_ecs":              "AWS ECS Fargate — serverless containers",
    "aws_lambda":           "AWS Lambda — serverless functions",
    "aws_app_runner":       "AWS App Runner — fully managed web apps",
    "aws_ec2":              "AWS EC2 — single VM (SSM run-command)",
    "aws_asg":              "AWS Auto Scaling Group — VMSS-equivalent rolling",
    "azure_aks":            "Azure AKS — managed Kubernetes",
    "azure_webapp":         "Azure App Service — managed web apps",
    "azure_container_apps": "Azure Container Apps — serverless containers",
    "azure_functions":      "Azure Functions — serverless functions",
    "azure_vm":             "Azure Virtual Machine — single VM",
    "azure_vmss":           "Azure VM Scale Set — rolling upgrade",
    "gcp_gke":              "Google GKE — managed Kubernetes",
    "gcp_cloud_run":        "Google Cloud Run — serverless containers",
    "gcp_cloud_functions":  "Google Cloud Functions — serverless functions",
    "gcp_app_engine":       "Google App Engine — managed PaaS",
    "gcp_gce":              "Google Compute Engine — single VM",
    "gcp_mig":              "Google Managed Instance Group — rolling update",
}


class TechnologyProfile(BaseModel):
    language: str = "unknown"
    language_confidence: float = 0.0
    framework: Optional[str] = None
    build_tool: Optional[str] = None
    test_framework: Optional[str] = None
    package_manager: Optional[str] = None
    container_ready: bool = False
    kubernetes_ready: bool = False
    helm_ready: bool = False
    infra_as_code: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ArchitectureProfile(BaseModel):
    style: Literal["monolith", "microservices", "serverless", "library", "unknown"] = "unknown"
    service_count_estimate: int = 1
    entry_points: List[str] = Field(default_factory=list)
    databases: List[str] = Field(default_factory=list)
    external_services: List[str] = Field(default_factory=list)
    reasoning: str = ""


class PipelineStage(BaseModel):
    name: str
    purpose: str
    tools: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    optional: bool = False
    explanation: str = ""


class PipelinePlan(BaseModel):
    ci_platform: CIPlatform
    cloud_platform: CloudPlatform
    stages: List[PipelineStage] = Field(default_factory=list)
    artifacts_strategy: str = ""
    security_strategy: str = ""
    approval_strategy: str = ""
    notifications: List[str] = Field(default_factory=list)
    custom_requirement_addressed: str = ""


class GeneratedPipeline(BaseModel):
    ci_platform: CIPlatform
    cloud_platform: CloudPlatform
    filename: str
    yaml_content: str
    stage_explanations: List[dict] = Field(default_factory=list)  # [{stage, why}]
