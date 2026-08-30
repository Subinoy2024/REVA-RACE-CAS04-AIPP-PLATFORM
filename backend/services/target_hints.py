"""Deployment-target hints — concrete cloud/target commands.

Why this exists:
  When a user picks a `deployment_target` other than `unspecified`, the
  planner directive already tells the LLM which target to honour, but
  the generator templates were originally written cloud-agnostic. This
  module lets us do two useful things:

    1. Inject a **header comment block** into the generated YAML naming
       the target and showing the reference deploy command. Users can
       copy-paste from there. No guessing.
    2. Append a **"Deployment guidance"** section to the pipeline
       explanation returned by the API so the UI surfaces it prominently.

How it's wired:
  - `PipelineService.generate()` post-processes the workflow result.
    If `deployment_target != unspecified`, it calls `header_comment()`
    and `explanation_section()` and injects them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TargetHint:
    label: str
    description: str
    deploy_command: str
    prereq: str


# One row per deployment target. Keep commands copy-paste-runnable.
HINTS: dict[str, TargetHint] = {
    # ---------------- AWS ----------------
    "aws_eks": TargetHint(
        label="AWS EKS",
        description="Managed Kubernetes cluster on AWS.",
        deploy_command=(
            "aws eks update-kubeconfig --name $EKS_CLUSTER --region $AWS_REGION && "
            "kubectl set image deployment/$APP_NAME $APP_NAME=$IMAGE:$TAG"
        ),
        prereq="EKS cluster + kubectl + IAM role with `eks:DescribeCluster`.",
    ),
    "aws_ecs": TargetHint(
        label="AWS ECS Fargate",
        description="Serverless containers on AWS.",
        deploy_command=(
            "aws ecs update-service --cluster $ECS_CLUSTER "
            "--service $ECS_SERVICE --force-new-deployment --region $AWS_REGION"
        ),
        prereq="ECS cluster + service + task definition already deployed; image pushed to ECR.",
    ),
    "aws_lambda": TargetHint(
        label="AWS Lambda",
        description="Serverless function on AWS.",
        deploy_command=(
            "aws lambda update-function-code --function-name $LAMBDA_NAME "
            "--image-uri $IMAGE:$TAG --region $AWS_REGION"
        ),
        prereq="Lambda function exists (container-image runtime); image pushed to ECR.",
    ),
    "aws_app_runner": TargetHint(
        label="AWS App Runner",
        description="Fully managed web apps on AWS.",
        deploy_command=(
            "aws apprunner start-deployment --service-arn $APPRUNNER_ARN "
            "--region $AWS_REGION"
        ),
        prereq="App Runner service already linked to an ECR image or repo.",
    ),
    "aws_ec2": TargetHint(
        label="AWS EC2",
        description="VMs on AWS (lift-and-shift).",
        deploy_command=(
            "aws ssm send-command --targets Key=tag:app,Values=$APP_NAME "
            "--document-name AWS-RunShellScript "
            "--parameters commands=\"docker pull $IMAGE:$TAG && systemctl restart $APP_NAME\""
        ),
        prereq="EC2 instances tagged `app=<name>`; SSM agent installed; IAM role with SSM RunCommand.",
    ),

    # ---------------- Azure ----------------
    "azure_aks": TargetHint(
        label="Azure AKS",
        description="Managed Kubernetes on Azure.",
        deploy_command=(
            "az aks get-credentials -n $AKS_CLUSTER -g $AZURE_RG && "
            "kubectl set image deployment/$APP_NAME $APP_NAME=$IMAGE:$TAG"
        ),
        prereq="AKS cluster + kubectl + AzureRM service connection.",
    ),
    "azure_webapp": TargetHint(
        label="Azure App Service",
        description="Managed web apps on Azure.",
        deploy_command=(
            "az webapp config container set --name $AZURE_WEBAPP_NAME "
            "--resource-group $AZURE_RG --docker-custom-image-name $IMAGE:$TAG"
        ),
        prereq="Web App configured for a custom container; ACR pull role granted.",
    ),
    "azure_container_apps": TargetHint(
        label="Azure Container Apps",
        description="Serverless containers on Azure.",
        deploy_command=(
            "az containerapp update --name $CONTAINER_APP --resource-group $AZURE_RG "
            "--image $IMAGE:$TAG"
        ),
        prereq="Container Apps environment + app already provisioned.",
    ),
    "azure_functions": TargetHint(
        label="Azure Functions",
        description="Serverless functions on Azure.",
        deploy_command=(
            "az functionapp config container set --name $FUNCTION_APP "
            "--resource-group $AZURE_RG --docker-custom-image-name $IMAGE:$TAG"
        ),
        prereq="Function App runtime = Docker container.",
    ),

    # ---------------- GCP ----------------
    "gcp_gke": TargetHint(
        label="Google GKE",
        description="Managed Kubernetes on GCP.",
        deploy_command=(
            "gcloud container clusters get-credentials $GKE_CLUSTER --region $GCP_REGION && "
            "kubectl set image deployment/$APP_NAME $APP_NAME=$IMAGE:$TAG"
        ),
        prereq="GKE cluster + Workload Identity or a service-account key.",
    ),
    "gcp_cloud_run": TargetHint(
        label="Google Cloud Run",
        description="Serverless containers on GCP.",
        deploy_command=(
            "gcloud run deploy $APP_NAME --image $IMAGE:$TAG --region $GCP_REGION "
            "--platform managed"
        ),
        prereq="Cloud Run API enabled; image in Artifact Registry.",
    ),
    "gcp_cloud_functions": TargetHint(
        label="Google Cloud Functions",
        description="Serverless functions on GCP.",
        deploy_command=(
            "gcloud functions deploy $APP_NAME --gen2 --runtime=python312 "
            "--region=$GCP_REGION --source=. --trigger-http"
        ),
        prereq="Cloud Functions Gen2 API enabled.",
    ),
    "gcp_app_engine": TargetHint(
        label="Google App Engine",
        description="Managed PaaS on GCP.",
        deploy_command="gcloud app deploy --quiet",
        prereq="App Engine app initialised (`gcloud app create`).",
    ),

    # ---------------- IaaS additions (iteration-26.4) ----------------
    "aws_asg": TargetHint(
        label="AWS Auto Scaling Group",
        description="Rolling instance refresh across an ASG.",
        deploy_command=(
            "aws ec2 modify-launch-template --launch-template-id $LT_ID "
            "--default-version $LT_VERSION --region $AWS_REGION && "
            "aws autoscaling start-instance-refresh --auto-scaling-group-name $ASG_NAME "
            "--preferences MinHealthyPercentage=90,InstanceWarmup=120 --region $AWS_REGION"
        ),
        prereq="ASG + launch template pre-created; IAM role allows autoscaling:StartInstanceRefresh.",
    ),
    "azure_vm": TargetHint(
        label="Azure Virtual Machine",
        description="Single VM deploy via SSM-equivalent `az vm run-command`.",
        deploy_command=(
            "az vm run-command invoke --resource-group $AZURE_RG --name $AZURE_VM_NAME "
            "--command-id RunShellScript --scripts \"docker pull $ACR_NAME.azurecr.io/$IMAGE:$TAG "
            "&& docker rm -f app || true && docker run -d --name app -p 80:$APP_PORT "
            "$ACR_NAME.azurecr.io/$IMAGE:$TAG\""
        ),
        prereq="VM has Docker installed; SP has `Virtual Machine Contributor` on the RG.",
    ),
    "azure_vmss": TargetHint(
        label="Azure VM Scale Set",
        description="Rolling upgrade across a VMSS.",
        deploy_command=(
            "az vmss update -g $AZURE_RG -n $AZURE_VMSS_NAME "
            "--set virtualMachineProfile.extensionProfile.extensions[0].settings.imageTag='$TAG' && "
            "az vmss rolling-upgrade start -g $AZURE_RG -n $AZURE_VMSS_NAME"
        ),
        prereq="VMSS upgradePolicy is `Rolling`; extension image tag setting present.",
    ),
    "gcp_gce": TargetHint(
        label="Google Compute Engine",
        description="Single VM deploy via `gcloud compute ssh`.",
        deploy_command=(
            "gcloud compute ssh $GCE_INSTANCE --zone $GCP_ZONE --command "
            "\"docker pull gcr.io/$GCP_PROJECT/$IMAGE:$TAG && docker rm -f app || true && "
            "docker run -d --name app -p 80:$APP_PORT gcr.io/$GCP_PROJECT/$IMAGE:$TAG\""
        ),
        prereq="OS Login enabled OR SSH key registered; Docker installed on the VM.",
    ),
    "gcp_mig": TargetHint(
        label="Google Managed Instance Group",
        description="Rolling update across a MIG.",
        deploy_command=(
            "gcloud compute instance-groups managed rolling-action start-update $MIG_NAME "
            "--version template=$INSTANCE_TEMPLATE --zone $GCP_ZONE "
            "--max-surge 1 --max-unavailable 0"
        ),
        prereq="MIG configured with an instance template pointing at the new image.",
    ),
}


def get_hint(target: str) -> Optional[TargetHint]:
    """Return the hint for `target`, or None if `unspecified` / unknown."""
    if not target or target == "unspecified":
        return None
    return HINTS.get(target)


def header_comment(target: str) -> str:
    """Return a `#`-prefixed YAML comment block advertising the target."""
    hint = get_hint(target)
    if hint is None:
        return ""
    return "\n".join([
        "# ─── AIPP Deployment Target ─────────────────────────────────────",
        f"# Target      : {hint.label}",
        f"# Description : {hint.description}",
        f"# Deploy cmd  : {hint.deploy_command}",
        f"# Prereq      : {hint.prereq}",
        "# ──────────────────────────────────────────────────────────────",
        "",
    ])


def explanation_section(target: str) -> str:
    """Return the Markdown block appended to the pipeline explanation."""
    hint = get_hint(target)
    if hint is None:
        return ""
    return (
        f"\n\nDeployment target guidance — **{hint.label}**\n"
        f"  Description: {hint.description}\n"
        f"  Reference deploy command:\n"
        f"    {hint.deploy_command}\n"
        f"  Prerequisite: {hint.prereq}\n"
    )
