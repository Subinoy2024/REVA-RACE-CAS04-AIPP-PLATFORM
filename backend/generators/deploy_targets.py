"""Dynamic deploy target selection and per-target real deploy commands.

The Architecture Detection agent classifies the repository shape. This module
then picks the correct concrete deploy target (Azure App Service, AKS, ECS,
EKS, Cloud Run, GKE, plain Kubernetes, or serverless) based on:

    (a) the detected architecture,
    (b) the user's chosen cloud (Azure / AWS / GCP),
    (c) whether the repo contains Kubernetes / Helm / serverless manifests.

Each DeployTarget carries the real shell command that performs the deploy.
Zero echo statements. Every line is copy-paste-runnable in a CI runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from backend.models.pipeline import ArchitectureProfile, CloudPlatform, TechnologyProfile


@dataclass(frozen=True)
class DeployTarget:
    """Concrete deployment landing spot for a given (cloud, architecture).

    `commands`         — CLI-based deploy (az / aws / gcloud). Default path.
    `python_commands`  — Python-SDK equivalent, activated when the user
                         opts out of CLI via `Custom deployment requirement`
                         (see `backend/generators/base.py::parse_deploy_style`).
                         Each entry is a plain Python source snippet — the
                         generator wraps them in `pip install` + `python -c`
                         steps appropriate for the target CI platform.
    `python_pip`       — extra pip packages needed by `python_commands`.
    """

    id: str                                # e.g. "azure_app_service", "aws_eks"
    display: str                           # human-readable label
    cloud: str                             # azure | aws | gcp
    kind: str                              # app_service | container | kubernetes | serverless
    commands: List[str]                    # CLI-based deploy commands (with placeholders)
    required_env: List[str]                # env vars the pipeline expects to be set
    notes: str = ""
    python_commands: Optional[List[str]] = None
    python_pip: Optional[List[str]] = None

    def commands_for(self, deploy_style: str) -> List[str]:
        """Return the command list matching the requested `deploy_style`.

        Falls back to `commands` if a python variant wasn't provided for
        this target (e.g. serverless Functions where only `func` CLI ships).
        """
        if deploy_style == "python" and self.python_commands:
            return list(self.python_commands)
        return list(self.commands)

    def pip_for(self, deploy_style: str) -> List[str]:
        if deploy_style == "python" and self.python_pip:
            return list(self.python_pip)
        return []


# ---------------------------------------------------------------------------
# Azure targets
# ---------------------------------------------------------------------------
AZURE_APP_SERVICE = DeployTarget(
    id="azure_app_service",
    display="Azure App Service (Web App for Containers)",
    cloud="azure",
    kind="app_service",
    commands=[
        "az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID",
        "az webapp config container set --name $AZURE_WEBAPP_NAME --resource-group $AZURE_RG "
        "--container-image-name $IMAGE:$TAG --container-registry-url https://$ACR_NAME.azurecr.io",
        "az webapp restart --name $AZURE_WEBAPP_NAME --resource-group $AZURE_RG",
    ],
    required_env=["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID",
                  "AZURE_WEBAPP_NAME", "AZURE_RG", "ACR_NAME"],
    notes="For simple monolithic apps with a Dockerfile.",
    # ------------------------------------------------------------------
    # Python-SDK equivalent — activated when the user asks for "python only /
    # no azure cli" in the Custom deployment requirement box.
    # Uses `azure-identity` (client-secret credential) + `azure-mgmt-web`
    # (management plane) — no `az` binary, no shell escaping quirks.
    # ------------------------------------------------------------------
    python_pip=["azure-identity>=1.17", "azure-mgmt-web>=7.3"],
    python_commands=[
        "from azure.identity import ClientSecretCredential",
        "from azure.mgmt.web import WebSiteManagementClient",
        "import os",
        "cred = ClientSecretCredential(tenant_id=os.environ['AZURE_TENANT_ID'],"
        " client_id=os.environ['AZURE_CLIENT_ID'],"
        " client_secret=os.environ['AZURE_CLIENT_SECRET'])",
        "client = WebSiteManagementClient(cred, os.environ['AZURE_SUBSCRIPTION_ID'])",
        "site = client.web_apps.get(os.environ['AZURE_RG'], os.environ['AZURE_WEBAPP_NAME'])",
        "site.site_config.linux_fx_version = f\"DOCKER|{os.environ['ACR_NAME']}.azurecr.io/{os.environ['IMAGE']}:{os.environ['TAG']}\"",
        "client.web_apps.begin_create_or_update(os.environ['AZURE_RG'], os.environ['AZURE_WEBAPP_NAME'], site).result()",
        "client.web_apps.restart(os.environ['AZURE_RG'], os.environ['AZURE_WEBAPP_NAME'])",
        "print(f'[deploy] {os.environ[\"AZURE_WEBAPP_NAME\"]} restarted with new image')",
    ],
)

AZURE_AKS = DeployTarget(
    id="azure_aks",
    display="Azure Kubernetes Service (AKS) via Helm",
    cloud="azure",
    kind="kubernetes",
    commands=[
        "az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID",
        "az aks get-credentials --name $AKS_CLUSTER --resource-group $AZURE_RG --overwrite-existing",
        "helm upgrade --install $RELEASE_NAME ./chart --namespace $NAMESPACE --create-namespace "
        "--set image.repository=$IMAGE --set image.tag=$TAG --wait --timeout 5m",
        "kubectl rollout status deploy/$RELEASE_NAME -n $NAMESPACE --timeout=5m",
    ],
    required_env=["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID",
                  "AKS_CLUSTER", "AZURE_RG", "RELEASE_NAME", "NAMESPACE"],
    notes="For Kubernetes-based workloads; requires a Helm chart at ./chart.",
    # ------------------------------------------------------------------
    # Python-SDK equivalent — pulls the AKS kubeconfig via
    # `azure-mgmt-containerservice`, writes it to $HOME/.kube/config, then
    # shells out to the same `helm`/`kubectl` binaries (no `az` needed).
    # ------------------------------------------------------------------
    python_pip=["azure-identity>=1.17", "azure-mgmt-containerservice>=32"],
    python_commands=[
        "import base64, os, pathlib, subprocess",
        "from azure.identity import ClientSecretCredential",
        "from azure.mgmt.containerservice import ContainerServiceClient",
        "cred = ClientSecretCredential(tenant_id=os.environ['AZURE_TENANT_ID'],"
        " client_id=os.environ['AZURE_CLIENT_ID'],"
        " client_secret=os.environ['AZURE_CLIENT_SECRET'])",
        "client = ContainerServiceClient(cred, os.environ['AZURE_SUBSCRIPTION_ID'])",
        "creds = client.managed_clusters.list_cluster_admin_credentials(os.environ['AZURE_RG'], os.environ['AKS_CLUSTER'])",
        "kubeconfig = base64.b64decode(creds.kubeconfigs[0].value).decode()",
        "kube_path = pathlib.Path.home() / '.kube' / 'config'; kube_path.parent.mkdir(parents=True, exist_ok=True); kube_path.write_text(kubeconfig)",
        "print('[deploy] fetched AKS admin kubeconfig via Python SDK')",
        # Then invoke helm/kubectl directly — no az cli.
        "subprocess.check_call(['helm','upgrade','--install',os.environ['RELEASE_NAME'],'./chart','--namespace',os.environ['NAMESPACE'],'--create-namespace','--set',f'image.repository={os.environ[\"IMAGE\"]}','--set',f'image.tag={os.environ[\"TAG\"]}','--wait','--timeout','5m'])",
        "subprocess.check_call(['kubectl','rollout','status',f'deploy/{os.environ[\"RELEASE_NAME\"]}','-n',os.environ['NAMESPACE'],'--timeout=5m'])",
    ],
)

AZURE_FUNCTIONS = DeployTarget(
    id="azure_functions",
    display="Azure Functions (serverless)",
    cloud="azure",
    kind="serverless",
    commands=[
        "az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID",
        "func azure functionapp publish $FUNCTION_APP_NAME --python",
    ],
    required_env=["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "FUNCTION_APP_NAME"],
    notes="For serverless workloads that ship as Azure Functions.",
)

# ---------------------------------------------------------------------------
# Iteration-26.4 · Azure IaaS targets — Virtual Machines & VM Scale Sets.
# ---------------------------------------------------------------------------
# Deploys the container image (or app artefact) onto a single VM or a VMSS
# rolling-upgrade set. Both targets ship a Python-SDK equivalent so the
# "no az cli" custom directive keeps working end-to-end.
# ---------------------------------------------------------------------------
AZURE_VM = DeployTarget(
    id="azure_vm",
    display="Azure Virtual Machine (single VM via run-command)",
    cloud="azure",
    kind="vm",
    commands=[
        "az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID",
        "az vm run-command invoke --resource-group $AZURE_RG --name $AZURE_VM_NAME "
        "--command-id RunShellScript --scripts "
        "\"docker pull $ACR_NAME.azurecr.io/$IMAGE:$TAG && "
        "docker rm -f app || true && "
        "docker run -d --name app --restart unless-stopped -p 80:$APP_PORT "
        "$ACR_NAME.azurecr.io/$IMAGE:$TAG\"",
    ],
    required_env=["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID",
                  "AZURE_RG", "AZURE_VM_NAME", "ACR_NAME", "APP_PORT"],
    notes="Single VM deploy. Pulls image + docker-run via VM run-command. Requires Docker installed on the VM.",
    python_pip=["azure-identity>=1.17", "azure-mgmt-compute>=32"],
    python_commands=[
        "import os",
        "from azure.identity import ClientSecretCredential",
        "from azure.mgmt.compute import ComputeManagementClient",
        "cred = ClientSecretCredential(tenant_id=os.environ['AZURE_TENANT_ID'],"
        " client_id=os.environ['AZURE_CLIENT_ID'],"
        " client_secret=os.environ['AZURE_CLIENT_SECRET'])",
        "client = ComputeManagementClient(cred, os.environ['AZURE_SUBSCRIPTION_ID'])",
        "script = ["
        " f\"docker pull {os.environ['ACR_NAME']}.azurecr.io/{os.environ['IMAGE']}:{os.environ['TAG']}\","
        " \"docker rm -f app || true\","
        " f\"docker run -d --name app --restart unless-stopped -p 80:{os.environ['APP_PORT']}\""
        " f\" {os.environ['ACR_NAME']}.azurecr.io/{os.environ['IMAGE']}:{os.environ['TAG']}\","
        "]",
        "poller = client.virtual_machines.begin_run_command(os.environ['AZURE_RG'], os.environ['AZURE_VM_NAME'], {'command_id': 'RunShellScript', 'script': script})",
        "result = poller.result()",
        "print('[deploy] VM run-command finished:', result.value[0].message if result.value else 'ok')",
    ],
)

AZURE_VMSS = DeployTarget(
    id="azure_vmss",
    display="Azure VM Scale Set (rolling upgrade)",
    cloud="azure",
    kind="vmss",
    commands=[
        "az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID",
        # Model update — bump the container tag on the scale-set VM extension.
        "az vmss update --resource-group $AZURE_RG --name $AZURE_VMSS_NAME "
        "--set virtualMachineProfile.extensionProfile.extensions[0].settings.imageTag='$TAG'",
        "az vmss rolling-upgrade start --resource-group $AZURE_RG --name $AZURE_VMSS_NAME",
        "az vmss wait --resource-group $AZURE_RG --name $AZURE_VMSS_NAME --updated",
    ],
    required_env=["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID",
                  "AZURE_RG", "AZURE_VMSS_NAME"],
    notes="Rolling upgrade across all VMSS instances. Zero downtime when upgrade policy is Rolling.",
    python_pip=["azure-identity>=1.17", "azure-mgmt-compute>=32"],
    python_commands=[
        "import os",
        "from azure.identity import ClientSecretCredential",
        "from azure.mgmt.compute import ComputeManagementClient",
        "cred = ClientSecretCredential(tenant_id=os.environ['AZURE_TENANT_ID'],"
        " client_id=os.environ['AZURE_CLIENT_ID'],"
        " client_secret=os.environ['AZURE_CLIENT_SECRET'])",
        "client = ComputeManagementClient(cred, os.environ['AZURE_SUBSCRIPTION_ID'])",
        "vmss = client.virtual_machine_scale_sets.get(os.environ['AZURE_RG'], os.environ['AZURE_VMSS_NAME'])",
        "# Bump the image tag on the first VM extension (assumed the app container extension).",
        "for ext in vmss.virtual_machine_profile.extension_profile.extensions:",
        "    if ext.settings is not None:",
        "        ext.settings['imageTag'] = os.environ['TAG']; break",
        "client.virtual_machine_scale_sets.begin_create_or_update(os.environ['AZURE_RG'], os.environ['AZURE_VMSS_NAME'], vmss).result()",
        "print('[deploy] VMSS model updated. Starting rolling upgrade...')",
        "client.rolling_upgrades.begin_start_os_upgrade(os.environ['AZURE_RG'], os.environ['AZURE_VMSS_NAME']).result()",
        "print('[deploy] VMSS rolling upgrade complete')",
    ],
)


# ---------------------------------------------------------------------------
# AWS targets
# ---------------------------------------------------------------------------
AWS_ECS_FARGATE = DeployTarget(
    id="aws_ecs_fargate",
    display="AWS ECS on Fargate",
    cloud="aws",
    kind="container",
    commands=[
        "aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE "
        "--force-new-deployment --region $AWS_REGION",
        "aws ecs wait services-stable --cluster $ECS_CLUSTER --services $ECS_SERVICE --region $AWS_REGION",
    ],
    required_env=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION",
                  "ECS_CLUSTER", "ECS_SERVICE"],
    notes="Existing ECS task definition is updated to the new image tag.",
)

AWS_EKS = DeployTarget(
    id="aws_eks",
    display="AWS Elastic Kubernetes Service (EKS) via Helm",
    cloud="aws",
    kind="kubernetes",
    commands=[
        "aws eks update-kubeconfig --name $EKS_CLUSTER --region $AWS_REGION",
        "helm upgrade --install $RELEASE_NAME ./chart --namespace $NAMESPACE --create-namespace "
        "--set image.repository=$IMAGE --set image.tag=$TAG --wait --timeout 5m",
        "kubectl rollout status deploy/$RELEASE_NAME -n $NAMESPACE --timeout=5m",
    ],
    required_env=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION",
                  "EKS_CLUSTER", "RELEASE_NAME", "NAMESPACE"],
    notes="For Kubernetes-based workloads on EKS; requires a Helm chart at ./chart.",
)

AWS_LAMBDA = DeployTarget(
    id="aws_lambda",
    display="AWS Lambda (serverless)",
    cloud="aws",
    kind="serverless",
    commands=[
        "sam build",
        "sam deploy --no-confirm-changeset --no-fail-on-empty-changeset --stack-name $STACK",
    ],
    required_env=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "STACK"],
    notes="For serverless workloads packaged with AWS SAM.",
)

# ---------------------------------------------------------------------------
# AWS IaaS targets — EC2 & Auto Scaling Group (VMSS-equivalent on AWS).
# ---------------------------------------------------------------------------
AWS_EC2 = DeployTarget(
    id="aws_ec2",
    display="AWS EC2 Virtual Machine (SSM Run Command)",
    cloud="aws",
    kind="vm",
    commands=[
        "aws ssm send-command --instance-ids $EC2_INSTANCE_ID --region $AWS_REGION "
        "--document-name AWS-RunShellScript "
        "--parameters commands=\""
        "aws ecr get-login-password --region $AWS_REGION | docker login --username AWS "
        "--password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com && "
        "docker pull $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$IMAGE:$TAG && "
        "docker rm -f app || true && "
        "docker run -d --name app --restart unless-stopped -p 80:$APP_PORT "
        "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$IMAGE:$TAG\"",
    ],
    required_env=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION",
                  "AWS_ACCOUNT_ID", "EC2_INSTANCE_ID", "APP_PORT"],
    notes="Single EC2 instance deploy via SSM Run Command. Requires Docker + SSM agent.",
)

AWS_ASG = DeployTarget(
    id="aws_asg",
    display="AWS Auto Scaling Group (instance refresh)",
    cloud="aws",
    kind="vmss",
    commands=[
        # Update launch-template default version to the newly-built AMI or user-data snapshot.
        "aws ec2 modify-launch-template --launch-template-id $LT_ID --default-version $LT_VERSION "
        "--region $AWS_REGION",
        # Trigger a rolling instance refresh — replaces instances one AZ at a time.
        "aws autoscaling start-instance-refresh --auto-scaling-group-name $ASG_NAME "
        "--preferences MinHealthyPercentage=90,InstanceWarmup=120 --region $AWS_REGION",
    ],
    required_env=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION",
                  "ASG_NAME", "LT_ID", "LT_VERSION"],
    notes="Rolling replacement across the ASG. Zero downtime when MinHealthyPercentage ≥ 90.",
)


# ---------------------------------------------------------------------------
# GCP targets
# ---------------------------------------------------------------------------
GCP_CLOUD_RUN = DeployTarget(
    id="gcp_cloud_run",
    display="GCP Cloud Run",
    cloud="gcp",
    kind="container",
    commands=[
        "gcloud auth activate-service-account --key-file=$GCP_SA_KEY_FILE",
        "gcloud config set project $GCP_PROJECT",
        "gcloud run deploy $CLOUD_RUN_SERVICE --image $IMAGE:$TAG --region $GCP_REGION "
        "--platform managed --allow-unauthenticated --quiet",
    ],
    required_env=["GCP_SA_KEY_FILE", "GCP_PROJECT", "GCP_REGION", "CLOUD_RUN_SERVICE"],
    notes="For containerized services; simple, fully managed.",
)

GCP_GKE = DeployTarget(
    id="gcp_gke",
    display="GCP Google Kubernetes Engine (GKE) via Helm",
    cloud="gcp",
    kind="kubernetes",
    commands=[
        "gcloud auth activate-service-account --key-file=$GCP_SA_KEY_FILE",
        "gcloud container clusters get-credentials $GKE_CLUSTER --region $GCP_REGION --project $GCP_PROJECT",
        "helm upgrade --install $RELEASE_NAME ./chart --namespace $NAMESPACE --create-namespace "
        "--set image.repository=$IMAGE --set image.tag=$TAG --wait --timeout 5m",
        "kubectl rollout status deploy/$RELEASE_NAME -n $NAMESPACE --timeout=5m",
    ],
    required_env=["GCP_SA_KEY_FILE", "GCP_PROJECT", "GCP_REGION", "GKE_CLUSTER",
                  "RELEASE_NAME", "NAMESPACE"],
    notes="For Kubernetes-based workloads on GKE; requires a Helm chart at ./chart.",
)

GCP_CLOUD_FUNCTIONS = DeployTarget(
    id="gcp_cloud_functions",
    display="GCP Cloud Functions (serverless)",
    cloud="gcp",
    kind="serverless",
    commands=[
        "gcloud auth activate-service-account --key-file=$GCP_SA_KEY_FILE",
        "gcloud functions deploy $FUNCTION_NAME --runtime python312 --trigger-http --allow-unauthenticated",
    ],
    required_env=["GCP_SA_KEY_FILE", "GCP_PROJECT", "FUNCTION_NAME"],
    notes="For serverless workloads on GCP.",
)

# ---------------------------------------------------------------------------
# GCP IaaS targets — Compute Engine VM & Managed Instance Group (VMSS eq.).
# ---------------------------------------------------------------------------
GCP_GCE = DeployTarget(
    id="gcp_gce",
    display="GCP Compute Engine VM (docker-run via SSH)",
    cloud="gcp",
    kind="vm",
    commands=[
        "gcloud auth activate-service-account --key-file=$GCP_SA_KEY_FILE",
        "gcloud config set project $GCP_PROJECT",
        "gcloud compute ssh $GCE_INSTANCE --zone $GCP_ZONE --command "
        "\"docker pull gcr.io/$GCP_PROJECT/$IMAGE:$TAG && "
        "docker rm -f app || true && "
        "docker run -d --name app --restart unless-stopped -p 80:$APP_PORT "
        "gcr.io/$GCP_PROJECT/$IMAGE:$TAG\"",
    ],
    required_env=["GCP_SA_KEY_FILE", "GCP_PROJECT", "GCP_ZONE", "GCE_INSTANCE", "APP_PORT"],
    notes="Single Compute Engine VM. Pulls image + docker-run via gcloud SSH.",
)

GCP_MIG = DeployTarget(
    id="gcp_mig",
    display="GCP Managed Instance Group (rolling update)",
    cloud="gcp",
    kind="vmss",
    commands=[
        "gcloud auth activate-service-account --key-file=$GCP_SA_KEY_FILE",
        "gcloud config set project $GCP_PROJECT",
        # Update the instance template reference on the MIG and trigger a rolling update.
        "gcloud compute instance-groups managed rolling-action start-update $MIG_NAME "
        "--version template=$INSTANCE_TEMPLATE --zone $GCP_ZONE "
        "--max-surge 1 --max-unavailable 0",
    ],
    required_env=["GCP_SA_KEY_FILE", "GCP_PROJECT", "GCP_ZONE", "MIG_NAME", "INSTANCE_TEMPLATE"],
    notes="Rolling update across MIG instances. Zero downtime with max-unavailable=0.",
)


# ---------------------------------------------------------------------------
# Cloud-agnostic K8s (used when the repo has raw kubernetes manifests but no
# Helm chart, and the user has already configured kubectl context).
# ---------------------------------------------------------------------------
KUBERNETES_KUBECTL = DeployTarget(
    id="kubernetes_kubectl",
    display="Bare Kubernetes (kubectl apply)",
    cloud="agnostic",
    kind="kubernetes",
    commands=[
        "kubectl apply -f k8s/ -n $NAMESPACE",
        "kubectl set image deploy/$DEPLOYMENT $CONTAINER=$IMAGE:$TAG -n $NAMESPACE",
        "kubectl rollout status deploy/$DEPLOYMENT -n $NAMESPACE --timeout=5m",
    ],
    required_env=["NAMESPACE", "DEPLOYMENT", "CONTAINER"],
    notes="Cloud-agnostic. Requires kubectl to already be configured for the cluster.",
)


# ---------------------------------------------------------------------------
# Selection logic — the "AI-driven" bit turned into deterministic rules that
# a human can audit. If the LLM Planning agent needs to override, it can, but
# the default is fully explainable.
# ---------------------------------------------------------------------------
def pick_deploy_target(
    cloud: CloudPlatform,
    arch: ArchitectureProfile,
    tech: TechnologyProfile,
) -> DeployTarget:
    """Return the recommended DeployTarget for a (cloud, arch, tech) combo."""
    kubernetes_signal = tech.kubernetes_ready or tech.helm_ready or arch.style == "microservices"
    serverless_signal = arch.style == "serverless"

    if serverless_signal:
        return {
            CloudPlatform.azure: AZURE_FUNCTIONS,
            CloudPlatform.aws: AWS_LAMBDA,
            CloudPlatform.gcp: GCP_CLOUD_FUNCTIONS,
        }[cloud]

    if kubernetes_signal:
        return {
            CloudPlatform.azure: AZURE_AKS,
            CloudPlatform.aws: AWS_EKS,
            CloudPlatform.gcp: GCP_GKE,
        }[cloud]

    # default: managed container hosting for the given cloud
    return {
        CloudPlatform.azure: AZURE_APP_SERVICE,
        CloudPlatform.aws: AWS_ECS_FARGATE,
        CloudPlatform.gcp: GCP_CLOUD_RUN,
    }[cloud]


ALL_TARGETS: List[DeployTarget] = [
    AZURE_APP_SERVICE, AZURE_AKS, AZURE_FUNCTIONS, AZURE_VM, AZURE_VMSS,
    AWS_ECS_FARGATE, AWS_EKS, AWS_LAMBDA, AWS_EC2, AWS_ASG,
    GCP_CLOUD_RUN, GCP_GKE, GCP_CLOUD_FUNCTIONS, GCP_GCE, GCP_MIG,
    KUBERNETES_KUBECTL,
]
