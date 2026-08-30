"""Iteration-26.4 · IaaS deploy targets — VM & VMSS/ASG/MIG.

Locks in that:
  * `DeploymentTarget` enum knows the new IDs
  * `TARGET_LABELS` has a human string for each
  * `CLOUD_TARGETS` allows them under the right cloud
  * `ALL_TARGETS` in `deploy_targets` exposes concrete commands
  * `pick_deploy_target()` still returns sensible defaults (no regression)
  * Frontend dropdown map surfaces them (via a light import check)
"""

from __future__ import annotations

import pytest

from backend.models.pipeline import (
    ArchitectureProfile,
    CloudPlatform,
    CLOUD_TARGETS,
    DeploymentTarget,
    TARGET_LABELS,
    TechnologyProfile,
)


NEW_IDS = ["azure_vm", "azure_vmss", "aws_ec2", "aws_asg", "gcp_gce", "gcp_mig"]


def test_enum_contains_all_iaas_ids():
    for i in NEW_IDS:
        assert getattr(DeploymentTarget, i).value == i


def test_labels_have_human_strings_for_new_ids():
    for i in NEW_IDS:
        assert i in TARGET_LABELS and TARGET_LABELS[i]


def test_cloud_map_surfaces_new_ids_under_correct_cloud():
    assert "azure_vm" in CLOUD_TARGETS["azure"]
    assert "azure_vmss" in CLOUD_TARGETS["azure"]
    assert "aws_ec2" in CLOUD_TARGETS["aws"]
    assert "aws_asg" in CLOUD_TARGETS["aws"]
    assert "gcp_gce" in CLOUD_TARGETS["gcp"]
    assert "gcp_mig" in CLOUD_TARGETS["gcp"]


def test_frontend_dropdown_map_has_new_ids():
    # importing the frontend module here validates the tuple list too
    from frontend.tabs.pipeline_generator import DEPLOYMENT_TARGETS_BY_CLOUD
    azure_ids = [v for _, v in DEPLOYMENT_TARGETS_BY_CLOUD["azure"]]
    aws_ids   = [v for _, v in DEPLOYMENT_TARGETS_BY_CLOUD["aws"]]
    gcp_ids   = [v for _, v in DEPLOYMENT_TARGETS_BY_CLOUD["gcp"]]
    for expected in ["azure_vm", "azure_vmss"]:
        assert expected in azure_ids
    for expected in ["aws_ec2", "aws_asg"]:
        assert expected in aws_ids
    for expected in ["gcp_gce", "gcp_mig"]:
        assert expected in gcp_ids


def test_all_targets_registered_in_deploy_targets_module():
    from backend.generators.deploy_targets import ALL_TARGETS
    ids = {t.id for t in ALL_TARGETS}
    for i in NEW_IDS:
        assert i in ids, f"missing DeployTarget for {i}"


def test_azure_vm_and_vmss_ship_python_sdk_variants():
    """Custom-requirement 'no az cli' must still work for VM/VMSS."""
    from backend.generators.deploy_targets import AZURE_VM, AZURE_VMSS
    for target in (AZURE_VM, AZURE_VMSS):
        py = target.commands_for("python")
        assert not any("az login" in c for c in py), target.id
        assert any("ComputeManagementClient" in c for c in py), target.id


def test_pick_deploy_target_still_sensible():
    """Adding IaaS targets must not break the default recommendation logic."""
    from backend.generators.deploy_targets import pick_deploy_target

    tech = TechnologyProfile(language="python")
    arch_micro = ArchitectureProfile(style="microservices")
    arch_mono = ArchitectureProfile(style="monolith")
    arch_serverless = ArchitectureProfile(style="serverless")

    # Microservices → Kubernetes (AKS/EKS/GKE) — unchanged.
    assert pick_deploy_target(CloudPlatform.azure, arch_micro, tech).id == "azure_aks"
    assert pick_deploy_target(CloudPlatform.aws, arch_micro, tech).id == "aws_eks"
    assert pick_deploy_target(CloudPlatform.gcp, arch_micro, tech).id == "gcp_gke"

    # Monolith → managed container hosting — unchanged.
    assert pick_deploy_target(CloudPlatform.azure, arch_mono, tech).id == "azure_app_service"

    # Serverless → *_lambda / *_functions — unchanged.
    assert pick_deploy_target(CloudPlatform.aws, arch_serverless, tech).id == "aws_lambda"
