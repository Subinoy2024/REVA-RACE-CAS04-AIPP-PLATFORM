"""GitLab CI YAML generator — production-ready.

Emits real commands per detected language, real container build + Trivy
scan + push, and real deploy commands per (cloud x architecture) target
using the same command / deploy_target tables as the other generators.
No echo stubs.
"""

from __future__ import annotations

from typing import List

import yaml

from backend.generators.base import BaseGenerator
from backend.generators.commands import pick_commands, image_ref
from backend.generators.deploy_targets import pick_deploy_target
from backend.models.pipeline import ArchitectureProfile, CloudPlatform


class GitLabCIGenerator(BaseGenerator):
    filename = ".gitlab-ci.yml"

    def render(self) -> str:
        # Iteration-20 (P1): honour `pipeline_type=infra` with the same
        # production-grade 4-stage Terraform flow that ADO + GH Actions emit
        # (validate → plan → policy → apply with manual gate). This keeps
        # GitLab CI at parity with the other generators when the user asks
        # for an infrastructure-only pipeline.
        if (self.pipeline_type or "").lower() == "infra":
            return self._render_infra_pipeline(self.plan.cloud_platform.value)

        cmds = pick_commands(self.tech.language, self.tech.package_manager)
        arch = ArchitectureProfile(
            style="microservices" if self.tech.kubernetes_ready else "monolith",
            service_count_estimate=1,
        )
        target = pick_deploy_target(
            cloud=CloudPlatform(self.plan.cloud_platform.value),
            arch=arch, tech=self.tech,
        )
        image = image_ref(self.plan.cloud_platform.value, "$REGISTRY_NAME", self.repo_name)

        stage_names = ["build", "test", "security", "package"] + [
            f"deploy_{r.name.value}" for r in self.env_plan.rules
        ]

        doc: dict = {
            "stages": stage_names,
            "variables": {
                "IMAGE_NAME": self.repo_name,
                "IMAGE": image,
                "TAG": "$CI_COMMIT_SHORT_SHA",
                "DOCKER_TLS_CERTDIR": "/certs",
            },
            "default": {
                "image": self._runtime_image(),
                "before_script": cmds.setup + cmds.install,
            },
        }
        # Apply the user-selected runner tags to every job (default block
        # only supports image/before_script, not tags — GitLab requires
        # `tags:` per job).
        tags = self._gitlab_tags()

        def _job(job_dict: dict) -> dict:
            if tags:
                job_dict = {**job_dict, "tags": tags}
            return job_dict

        doc.update({
            "build": _job({
                "stage": "build",
                "script": cmds.build,
                "artifacts": {"paths": [cmds.artifact_path], "expire_in": "1 day"},
            }),
            "unit_test": _job({
                "stage": "test",
                "script": cmds.unit_test,
                "artifacts": {
                    "when": "always",
                    "reports": {"junit": "**/test-results.xml"},
                    "expire_in": "7 days",
                },
            }),
            "sast": _job({
                "stage": "security",
                "script": cmds.sast,
                "allow_failure": True,
            }),
            "dependency_scan": _job({
                "stage": "security",
                "script": cmds.dependency_scan,
                "allow_failure": True,
            }),
            "lint": _job({
                "stage": "security",
                "script": cmds.lint,
                "allow_failure": True,
            }),
            "container_build_scan_push": _job({
                "stage": "package",
                "image": "docker:24",
                "services": ["docker:24-dind"],
                "before_script": [self._registry_login_cmd(target.cloud)],
                "script": [
                    "docker buildx build --platform linux/amd64 -t $IMAGE:$TAG -f Dockerfile .",
                    "trivy image --exit-code 0 --severity CRITICAL,HIGH $IMAGE:$TAG || true",
                    "docker push $IMAGE:$TAG",
                ],
            }),
        })

        for r in self.env_plan.rules:
            job_id = f"deploy_{r.name.value}"
            steps: List[str] = []
            steps.append(self._cloud_auth_cmd(target.cloud))
            steps.extend(target.commands)
            if r.health_check:
                steps.append(self._health_check_cmd(target.kind))
            if r.smoke_test:
                steps.append("curl -fsS $APP_HEALTH_URL/health || (echo 'smoke test failed' && exit 1)")

            doc[job_id] = _job({
                "stage": job_id,
                "image": self._deploy_runtime_image(target.cloud),
                "environment": {"name": r.name.value},
                "when": "manual" if r.requires_approval else "on_success",
                "rules": [{"if": self._if_expr(r.trigger)}],
                "script": steps,
            })

        rendered = yaml.safe_dump(doc, sort_keys=False, width=140)
        # Iteration-20: inject `#` comments above every stage/job.
        from backend.generators.base import (
            COMMON_STAGE_COMMENTS, default_pipeline_header, inject_comments,
        )
        header = default_pipeline_header(
            ci="GitLab CI",
            cloud=self.plan.cloud_platform.value,
            scope=(self.pipeline_type or "all_in_one"),
            custom_requirement=self.custom_requirement,
            deploy_style=self.deploy_style,
        )
        return header + inject_comments(rendered, COMMON_STAGE_COMMENTS)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    # -------------------------------------------------------------------
    # Production-grade Terraform infra pipeline (mirrors ADO + GH iter-17).
    # Four GitLab stages: validate → plan → policy → apply. `apply` uses
    # `when: manual` so a human must click before Terraform actually
    # touches the cloud — analogous to the ADO/GH manual-approval gate.
    # -------------------------------------------------------------------
    def _render_infra_pipeline(self, cloud: str) -> str:
        provider_note = {
            "aws":   "provider hashicorp/aws + S3 backend",
            "azure": "provider hashicorp/azurerm + azurerm backend",
            "gcp":   "provider hashicorp/google + GCS backend",
        }.get(cloud, "Terraform")

        # Runner tags — respect the user-selected agent_pool if any.
        tags = self._gitlab_tags()

        def _apply_tags(job: dict) -> dict:
            if tags:
                return {**job, "tags": tags}
            return job

        # Terraform working dir + backend key have safe defaults so the
        # pipeline is usable out of the box; the user can override any of
        # them via GitLab CI/CD `Variables` at the project/group level.
        # NOTE: GitLab does not support shell-style `${VAR:-default}` in
        # `variables:` blocks; we set the defaults explicitly and let the
        # project-level Variables override them at runtime.
        base_variables = {
            "TF_ROOT": ".",
            "TF_VERSION": "latest",
            "TF_BACKEND_KEY": "$CI_PROJECT_PATH_SLUG.tfstate",
        }

        # Auth commands per cloud — shared across every job that needs
        # to talk to the cloud API. Kept identical to the CI-body helper
        # so a human reading both flows sees the same auth block.
        cloud_auth = self._cloud_auth_cmd(cloud)

        # Common install snippet — installs the required terraform version,
        # tflint and (only in the validate job) tfsec.
        install_terraform = (
            "curl -fsSLo /tmp/tf.zip "
            "https://releases.hashicorp.com/terraform/${TF_VERSION}/"
            "terraform_${TF_VERSION}_linux_amd64.zip "
            "|| curl -fsSLo /tmp/tf.zip "
            "https://releases.hashicorp.com/terraform/1.9.5/terraform_1.9.5_linux_amd64.zip; "
            "unzip -o /tmp/tf.zip -d /usr/local/bin/; "
            "terraform version"
        )
        install_tflint = (
            "curl -sSL https://raw.githubusercontent.com/terraform-linters/"
            "tflint/master/install_linux.sh | bash"
        )
        install_tfsec = "curl -sSL https://tfsec.dev/install.sh | bash"
        install_conftest = (
            "wget -qO /tmp/conftest.tar.gz "
            "https://github.com/open-policy-agent/conftest/releases/latest/"
            "download/conftest_Linux_x86_64.tar.gz && "
            "tar -xzf /tmp/conftest.tar.gz -C /tmp && "
            "mv /tmp/conftest /usr/local/bin/"
        )

        # ---------------- Stage 1: validate + lint + security -----------
        validate_job = _apply_tags({
            "stage": "validate",
            "image": "ubuntu:22.04",
            "before_script": [
                "apt-get update -qq && apt-get install -y -qq curl unzip ca-certificates jq",
                install_terraform,
                install_tflint,
                install_tfsec,
                cloud_auth,
            ],
            "script": [
                "cd \"$TF_ROOT\"",
                "terraform fmt -check -recursive",
                "terraform init -input=false -backend-config=key=$TF_BACKEND_KEY",
                "terraform validate",
                "tflint --init && tflint --format=default --recursive",
                "tfsec . --format=lovely --soft-fail-warnings",
            ],
        })

        # ---------------- Stage 2: plan → tfplan artifact ---------------
        plan_job = _apply_tags({
            "stage": "plan",
            "image": "ubuntu:22.04",
            "needs": ["terraform_validate"],
            "before_script": [
                "apt-get update -qq && apt-get install -y -qq curl unzip ca-certificates",
                install_terraform,
                cloud_auth,
            ],
            "script": [
                "cd \"$TF_ROOT\"",
                "terraform init -input=false -backend-config=key=$TF_BACKEND_KEY",
                "terraform plan -input=false -out=tfplan -detailed-exitcode | tee plan.txt",
                "terraform show -json tfplan > plan.json",
            ],
            "artifacts": {
                "name": "tfplan-$CI_COMMIT_SHORT_SHA",
                "paths": ["$TF_ROOT/tfplan", "$TF_ROOT/plan.json", "$TF_ROOT/plan.txt"],
                "when": "on_success",
                "expire_in": "14 days",
            },
        })

        # ---------------- Stage 3: policy (OPA / conftest + Terratest) --
        policy_job = _apply_tags({
            "stage": "policy",
            "image": "ubuntu:22.04",
            "needs": [{"job": "terraform_plan", "artifacts": True}],
            "before_script": [
                "apt-get update -qq && apt-get install -y -qq curl wget tar ca-certificates",
                install_conftest,
            ],
            "script": [
                "if [ -d policy ]; then "
                "  conftest test $TF_ROOT/plan.json --policy policy; "
                "else "
                "  echo 'No ./policy directory found — skipping OPA gate'; "
                "fi",
                "if [ -d tests ] && ls tests/*.go >/dev/null 2>&1; then "
                "  apt-get install -y -qq golang-go && go test -v -timeout 60m ./tests/...; "
                "else "
                "  echo 'No Terratest suite under ./tests — skipping'; "
                "fi",
            ],
            "allow_failure": True,   # soft-fail: OPA/Terratest never block
        })

        # ---------------- Stage 4: manual-approval apply ----------------
        apply_job = _apply_tags({
            "stage": "apply",
            "image": "ubuntu:22.04",
            "needs": [
                {"job": "terraform_plan", "artifacts": True},
                "terraform_policy",
            ],
            "environment": {"name": "production"},   # GitLab tracks the env
            # `when: manual` forces a human click before terraform apply
            # runs, mirroring ADO's `environment:` approval + GH Environments.
            "when": "manual",
            # Only run on main / v*.*.* tags — never on feature branches.
            "rules": [
                {"if": '$CI_COMMIT_BRANCH == "main"'},
                {"if": '$CI_COMMIT_TAG =~ /^v[0-9]+\\.[0-9]+\\.[0-9]+$/'},
            ],
            "before_script": [
                "apt-get update -qq && apt-get install -y -qq curl unzip ca-certificates",
                install_terraform,
                cloud_auth,
            ],
            "script": [
                "cd \"$TF_ROOT\"",
                "terraform init -input=false -backend-config=key=$TF_BACKEND_KEY",
                "terraform apply -input=false -auto-approve tfplan",
                "terraform output -json > outputs.json",
            ],
            "artifacts": {
                "name": "terraform-outputs-$CI_COMMIT_SHORT_SHA",
                "paths": ["$TF_ROOT/outputs.json"],
                "expire_in": "90 days",
            },
        })

        doc = {
            "stages": ["validate", "plan", "policy", "apply"],
            "variables": base_variables,
            "terraform_validate": validate_job,
            "terraform_plan":     plan_job,
            "terraform_policy":   policy_job,
            "terraform_apply":    apply_job,
        }
        # Human-readable header comment via a yaml document prefix.
        header = (
            f"# ==================================================================\n"
            f"# AIPP Terraform pipeline · {provider_note}\n"
            f"# 4-stage flow: validate → plan → policy → apply\n"
            f"# `apply` is a manual job — GitLab's `when: manual` gate blocks it\n"
            f"# until a maintainer clicks Play in the pipeline UI.\n"
            f"# ==================================================================\n"
        )
        rendered = yaml.safe_dump(doc, sort_keys=False, width=140)

        # Inject `#` comments above each terraform job so a human reading
        # the .gitlab-ci.yml understands each block without guessing.
        from backend.generators.base import inject_comments
        rendered = inject_comments(rendered, {
            "terraform_validate:":
                ["-----------------------------------------------------------",
                 "STAGE 1 · VALIDATE — fmt + init + validate + tflint + tfsec",
                 "-----------------------------------------------------------"],
            "terraform_plan:":
                ["-----------------------------------------------------------",
                 "STAGE 2 · PLAN — publishes tfplan + plan.json as artifacts",
                 "-----------------------------------------------------------"],
            "terraform_policy:":
                ["-----------------------------------------------------------",
                 "STAGE 3 · POLICY — OPA/conftest + optional Terratest",
                 "allow_failure: true → advisory gate, never blocks apply",
                 "-----------------------------------------------------------"],
            "terraform_apply:":
                ["-----------------------------------------------------------",
                 "STAGE 4 · APPLY — `when: manual` + main/v*.*.* rule guard",
                 "Deploys via GitLab `environment: production` (audit trail)",
                 "-----------------------------------------------------------"],
        })
        return header + rendered

    def _runtime_image(self) -> str:
        lang = (self.tech.language or "").lower()
        pm = (self.tech.package_manager or "").lower()
        if lang in {"javascript", "typescript", "node", "nodejs"}:
            return "node:20-bullseye"
        if lang == "python":
            return "python:3.12-slim"
        if lang == "java":
            return "maven:3.9-eclipse-temurin-17" if pm != "gradle" else "gradle:8-jdk17"
        if lang == "go":
            return "golang:1.22"
        if lang in {"rust", "cargo"}:
            return "rust:1"
        if lang in {"csharp", "c#", "dotnet", ".net"}:
            return "mcr.microsoft.com/dotnet/sdk:8.0"
        return "ubuntu:22.04"

    @staticmethod
    def _registry_login_cmd(cloud: str) -> str:
        if cloud == "azure":
            return "echo $ACR_PASSWORD | docker login $REGISTRY_NAME.azurecr.io -u $ACR_USERNAME --password-stdin"
        if cloud == "aws":
            return ("aws ecr get-login-password --region $AWS_REGION | "
                    "docker login --username AWS --password-stdin $REGISTRY_NAME")
        if cloud == "gcp":
            return "gcloud auth configure-docker $GCP_REGION-docker.pkg.dev --quiet"
        return "echo 'no registry login required'"

    @staticmethod
    def _cloud_auth_cmd(cloud: str) -> str:
        if cloud == "azure":
            return ("az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET "
                    "--tenant $AZURE_TENANT_ID")
        if cloud == "aws":
            return "aws sts get-caller-identity"  # creds come from env in GitLab
        if cloud == "gcp":
            return "gcloud auth activate-service-account --key-file=$GCP_SA_KEY_FILE"
        return "true"

    @staticmethod
    def _deploy_runtime_image(cloud: str) -> str:
        if cloud == "azure":
            return "mcr.microsoft.com/azure-cli:latest"
        if cloud == "aws":
            return "amazon/aws-cli:latest"
        if cloud == "gcp":
            return "google/cloud-sdk:slim"
        return "alpine/k8s:1.29.0"

    @staticmethod
    def _health_check_cmd(kind: str) -> str:
        if kind == "kubernetes":
            return "kubectl rollout status deploy/$RELEASE_NAME -n $NAMESPACE --timeout=5m"
        if kind == "container":
            return "sleep 10 && curl -fsS $APP_HEALTH_URL || (echo 'health check failed' && exit 1)"
        return "true"

    @staticmethod
    def _if_expr(trigger: str) -> str:
        return {
            "develop_branch":  '$CI_COMMIT_BRANCH == "develop"',
            "release_branch":  '$CI_COMMIT_BRANCH =~ /^release\\//',
            "main_branch":     '$CI_COMMIT_BRANCH == "main"',
            "version_tag":     '$CI_COMMIT_TAG =~ /^v[0-9]+\\.[0-9]+\\.[0-9]+$/',
            "manual":          '$CI_PIPELINE_SOURCE == "web"',
            "feature_branch":  '$CI_COMMIT_BRANCH =~ /^feature\\//',
        }.get(trigger, '$CI_COMMIT_BRANCH')
