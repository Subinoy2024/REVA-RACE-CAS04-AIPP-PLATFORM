"""GitHub Actions YAML generator — production-ready.

Emits real commands per detected language, real container build + push, and
real deploy commands per (cloud x architecture) target. No echo stubs.

The output is written to `.github/workflows/aipp-pipeline.yml` and can be
committed directly to the target branch chosen in the UI.
"""

from __future__ import annotations

from typing import List

import yaml

from backend.generators.base import BaseGenerator
from backend.generators.commands import pick_commands, image_ref
from backend.generators.deploy_targets import pick_deploy_target
from backend.models.environment import EnvironmentRule
from backend.models.pipeline import ArchitectureProfile, CloudPlatform


class GitHubActionsGenerator(BaseGenerator):
    filename = ".github/workflows/aipp-pipeline.yml"

    def render(self) -> str:
        cmds = pick_commands(self.tech.language, self.tech.package_manager)
        arch = ArchitectureProfile(
            style="microservices" if self.tech.kubernetes_ready else "monolith",
            service_count_estimate=1,
        )
        target = pick_deploy_target(
            cloud=CloudPlatform(self.plan.cloud_platform.value),
            arch=arch,
            tech=self.tech,
        )
        image = image_ref(
            self.plan.cloud_platform.value,
            "${{ secrets.REGISTRY_NAME }}",
            self.repo_name,
        )

        # Infra-only short-circuit: emit the same production-grade 4-job
        # Terraform pipeline (validate / plan / policy / apply) that the
        # Azure DevOps generator emits, but expressed in GitHub Actions'
        # syntax.
        if (self.pipeline_type or "").lower() == "infra":
            return self._render_infra_workflow(self.plan.cloud_platform.value)

        wf: dict = {
            "name": f"AIPP - {self.repo_name}",
            "on": {
                "push": {"branches": ["develop", "release/*", "main"], "tags": ["v*.*.*"]},
                "pull_request": {"branches": ["develop", "main"]},
                "workflow_dispatch": {},
            },
            "permissions": {"contents": "read", "id-token": "write", "packages": "write"},
            "env": {
                "IMAGE_NAME": self.repo_name,
                "IMAGE": image,
                "TAG": "${{ github.sha }}",
            },
            "jobs": {},
        }

        # ---- Gate 1: Build + unit test ----
        wf["jobs"]["build"] = {
            "name": "Build & Unit test",
            "runs-on": self._gh_runs_on(),
            "steps": (
                [{"uses": "actions/checkout@v4"}]
                + self._toolchain(cmds.setup)
                + [{"name": "Install", "run": " && ".join(cmds.install)}]
                + [{"name": "Build", "run": " && ".join(cmds.build)}]
                + [{"name": "Unit tests", "run": " && ".join(cmds.unit_test)}]
                + [{
                    "name": "Upload artifact",
                    "uses": "actions/upload-artifact@v4",
                    "with": {"name": "app", "path": cmds.artifact_path,
                             "if-no-files-found": "warn"},
                }]
            ),
        }

        # ---- Gate 2: Security (SAST + SCA + Lint) ----
        wf["jobs"]["security"] = {
            "name": "Security scans",
            "runs-on": self._gh_runs_on(),
            "needs": "build",
            "steps": (
                [{"uses": "actions/checkout@v4"}]
                + self._toolchain(cmds.setup)
                + [{"name": "SAST", "run": " && ".join(cmds.sast)}]
                + [{"name": "Dependency scan", "run": " && ".join(cmds.dependency_scan)}]
                + [{"name": "Lint", "run": " && ".join(cmds.lint)}]
            ),
        }

        # ---- Gate 3: Container build + Trivy + push ----
        wf["jobs"]["package"] = {
            "name": "Container build + scan + push",
            "runs-on": self._gh_runs_on(),
            "needs": "security",
            "steps": [
                {"uses": "actions/checkout@v4"},
                {"uses": "docker/setup-buildx-action@v3"},
                self._registry_login(target.cloud),
                {"name": "Docker build",
                 "run": "docker buildx build --platform linux/amd64 "
                        "-t ${{ env.IMAGE }}:${{ env.TAG }} -f Dockerfile ."},
                {"name": "Trivy image scan",
                 "uses": "aquasecurity/trivy-action@master",
                 "with": {
                     "image-ref": "${{ env.IMAGE }}:${{ env.TAG }}",
                     "severity": "CRITICAL,HIGH",
                     "exit-code": "0",
                 }},
                {"name": "Docker push",
                 "run": "docker push ${{ env.IMAGE }}:${{ env.TAG }}"},
            ],
        }

        # ---- Deploy ladder ----
        for rule in self.env_plan.rules:
            job_id = f"deploy_{rule.name.value}"
            wf["jobs"][job_id] = self._deploy_job(rule, target)

        rendered = yaml.safe_dump(wf, sort_keys=False, width=140)
        # Iteration-20: inject `#` comments above every job so a human
        # reading the workflow understands each block at a glance.
        from backend.generators.base import (
            COMMON_STAGE_COMMENTS, default_pipeline_header, inject_comments,
        )
        header = default_pipeline_header(
            ci="GitHub Actions",
            cloud=self.plan.cloud_platform.value,
            scope=(self.pipeline_type or "all_in_one"),
            custom_requirement=self.custom_requirement,
            deploy_style=self.deploy_style,
        )
        return header + inject_comments(rendered, COMMON_STAGE_COMMENTS)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _toolchain(setup: list[str]) -> list[dict]:
        out: list[dict] = []
        for step in setup:
            if step.startswith("actions/setup-node"):
                v = step.split(":")[-1] if ":" in step else "20"
                out.append({"uses": "actions/setup-node@v4", "with": {"node-version": v, "cache": "npm"}})
            elif step.startswith("actions/setup-python"):
                v = step.split(":")[-1] if ":" in step else "3.12"
                out.append({"uses": "actions/setup-python@v5", "with": {"python-version": v, "cache": "pip"}})
            elif step.startswith("actions/setup-java"):
                parts = step.split(":")
                dist = parts[1] if len(parts) > 2 else "temurin"
                ver = parts[-1] if len(parts) > 1 else "17"
                out.append({"uses": "actions/setup-java@v4",
                            "with": {"distribution": dist, "java-version": ver, "cache": "maven"}})
            elif step.startswith("actions/setup-go"):
                v = step.split(":")[-1] if ":" in step else "1.22"
                out.append({"uses": "actions/setup-go@v5", "with": {"go-version": v, "cache": True}})
            elif step.startswith("actions/setup-dotnet"):
                v = step.split(":")[-1] if ":" in step else "8.0"
                out.append({"uses": "actions/setup-dotnet@v4", "with": {"dotnet-version": v}})
            else:
                out.append({"name": step[:40], "run": step})
        return out

    @staticmethod
    def _registry_login(cloud: str) -> dict:
        if cloud == "azure":
            return {"name": "ACR login",
                    "uses": "azure/docker-login@v2",
                    "with": {"login-server": "${{ secrets.REGISTRY_NAME }}.azurecr.io",
                             "username": "${{ secrets.ACR_USERNAME }}",
                             "password": "${{ secrets.ACR_PASSWORD }}"}}
        if cloud == "aws":
            return {"name": "ECR login",
                    "uses": "aws-actions/amazon-ecr-login@v2"}
        if cloud == "gcp":
            return {"name": "GAR login",
                    "run": "gcloud auth configure-docker "
                           "${{ vars.GCP_REGION }}-docker.pkg.dev --quiet"}
        # agnostic (docker hub / other)
        return {"name": "Docker login",
                "uses": "docker/login-action@v3",
                "with": {"username": "${{ secrets.DOCKER_USER }}",
                         "password": "${{ secrets.DOCKER_TOKEN }}"}}

    def _deploy_job(self, rule: EnvironmentRule, target) -> dict:
        # Branch / tag filter
        filter_expr = {
            "develop_branch":  "github.ref == 'refs/heads/develop'",
            "release_branch":  "startsWith(github.ref, 'refs/heads/release/')",
            "main_branch":     "github.ref == 'refs/heads/main'",
            "version_tag":     "startsWith(github.ref, 'refs/tags/v')",
            "manual":          "github.event_name == 'workflow_dispatch'",
        }.get(rule.trigger, "github.event_name == 'workflow_dispatch'")

        deploy_steps: list[dict] = [{"uses": "actions/checkout@v4"}]
        # Cloud login for the deploy step
        deploy_steps.append(self._cloud_login(target.cloud))
        # Real deploy commands from the DeployTarget table
        for c in target.commands:
            deploy_steps.append({"name": c[:50], "run": c})
        if rule.health_check:
            deploy_steps.append({"name": "Health check",
                                 "run": "sleep 15 && kubectl rollout status "
                                        "deploy/${{ vars.RELEASE_NAME }} "
                                        "-n ${{ vars.NAMESPACE }} --timeout=5m || true"})
        if rule.smoke_test:
            deploy_steps.append({"name": "Smoke test",
                                 "run": "curl -fsS \"${{ vars.APP_HEALTH_URL }}/health\" "
                                        "|| (echo 'smoke test failed' && exit 1)"})

        job: dict = {
            "name": f"Deploy to {rule.name.value.title()}",
            "runs-on": self._gh_runs_on(),
            "needs": "package",
            "if": filter_expr,
            "environment": {"name": rule.name.value},
            "steps": deploy_steps,
        }
        return job

    @staticmethod
    def _cloud_login(cloud: str) -> dict:
        if cloud == "azure":
            return {"name": "Azure login",
                    "uses": "azure/login@v2",
                    "with": {"creds": "${{ secrets.AZURE_CREDENTIALS }}"}}
        if cloud == "aws":
            return {"name": "AWS credentials",
                    "uses": "aws-actions/configure-aws-credentials@v4",
                    "with": {"aws-access-key-id": "${{ secrets.AWS_ACCESS_KEY_ID }}",
                             "aws-secret-access-key": "${{ secrets.AWS_SECRET_ACCESS_KEY }}",
                             "aws-region": "${{ vars.AWS_REGION }}"}}
        if cloud == "gcp":
            return {"name": "GCP auth",
                    "uses": "google-github-actions/auth@v2",
                    "with": {"credentials_json": "${{ secrets.GCP_SA_KEY }}"}}
        return {"name": "Skip cloud login (agnostic target)", "run": "true"}


    # -------------------------------------------------------------------
    # Production-grade Terraform infra workflow (mirrors ADO iter-17).
    # -------------------------------------------------------------------
    def _render_infra_workflow(self, cloud: str) -> str:
        provider_note = {
            "aws":   "provider hashicorp/aws + S3 backend",
            "azure": "provider hashicorp/azurerm + azurerm backend",
            "gcp":   "provider hashicorp/google + GCS backend",
        }.get(cloud, "Terraform")

        runs_on = self._gh_runs_on()
        cloud_auth = self._cloud_login(cloud)

        checkout = {"name": "Checkout", "uses": "actions/checkout@v4"}
        setup_terraform = {
            "name": "Setup Terraform",
            "uses": "hashicorp/setup-terraform@v3",
            "with": {"terraform_version": "${{ vars.TF_VERSION || 'latest' }}",
                     "terraform_wrapper": False},
        }
        setup_tflint = {
            "name": "Setup tflint",
            "uses": "terraform-linters/setup-tflint@v4",
        }
        setup_tfsec = {
            "name": "Setup tfsec",
            "uses": "aquasecurity/tfsec-action@v1.0.3",
        }

        tf_root = "${{ vars.TF_ROOT || '.' }}"
        backend_key = "${{ vars.TF_BACKEND_KEY || format('{0}.tfstate', github.event.repository.name) }}"

        # ----------------- Job 1: validate --------------------------------
        validate_job = {
            "name": f"Validate ({provider_note})",
            "runs-on": runs_on,
            "defaults": {"run": {"working-directory": tf_root}},
            "steps": [
                checkout,
                cloud_auth,
                setup_terraform,
                {"name": "terraform fmt", "run": "terraform fmt -check -recursive"},
                {"name": "terraform init",
                 "run": f"terraform init -input=false -backend-config=key={backend_key}"},
                {"name": "terraform validate", "run": "terraform validate"},
                setup_tflint,
                {"name": "tflint",
                 "run": "tflint --init && tflint --format=default --recursive"},
                setup_tfsec,
            ],
        }

        # ----------------- Job 2: plan -> tfplan artifact -----------------
        plan_job = {
            "name": "Plan (produces tfplan artifact)",
            "needs": "validate",
            "runs-on": runs_on,
            "defaults": {"run": {"working-directory": tf_root}},
            "steps": [
                checkout,
                cloud_auth,
                setup_terraform,
                {"name": "terraform init",
                 "run": f"terraform init -input=false -backend-config=key={backend_key}"},
                {"name": "terraform plan",
                 "run": ("terraform plan -input=false -out=tfplan -detailed-exitcode "
                         "| tee plan.txt\n"
                         "terraform show -json tfplan > plan.json")},
                {"name": "Upload tfplan artifact",
                 "uses": "actions/upload-artifact@v4",
                 "with": {"name": "tfplan",
                          "path": f"{tf_root}/tfplan\n{tf_root}/plan.json\n{tf_root}/plan.txt",
                          "if-no-files-found": "error",
                          "retention-days": 14}},
            ],
        }

        # ----------------- Job 3: policy (OPA + Terratest, soft-fail) -----
        policy_job = {
            "name": "Policy (OPA / conftest + Terratest)",
            "needs": "plan",
            "runs-on": runs_on,
            "steps": [
                checkout,
                {"name": "Download tfplan artifact",
                 "uses": "actions/download-artifact@v4",
                 "with": {"name": "tfplan", "path": "tfplan-artifact"}},
                {"name": "Install conftest",
                 "run": ("wget -qO /tmp/conftest.tar.gz "
                         "https://github.com/open-policy-agent/conftest/releases/latest"
                         "/download/conftest_Linux_x86_64.tar.gz "
                         "&& tar -xzf /tmp/conftest.tar.gz -C /tmp "
                         "&& sudo mv /tmp/conftest /usr/local/bin/")},
                {"name": "OPA / conftest gate",
                 "continue-on-error": True,
                 "run": ("if [ -d policy ]; then "
                         "  conftest test tfplan-artifact/plan.json --policy policy; "
                         "else "
                         "  echo 'No ./policy directory found — skipping OPA gate'; "
                         "fi")},
                {"name": "Terratest (if present)",
                 "continue-on-error": True,
                 "run": ("if [ -d tests ] && ls tests/*.go >/dev/null 2>&1; then "
                         "  go test -v -timeout 60m ./tests/...; "
                         "else "
                         "  echo 'No Terratest suite under ./tests — skipping'; "
                         "fi")},
            ],
        }

        # ----------------- Job 4: apply (manual approval via env) ---------
        apply_job = {
            "name": "Apply (manual approval required)",
            "needs": "policy",
            "runs-on": runs_on,
            # GitHub Environments enforces required-reviewer approval.
            "environment": "production",
            # Fire only on main pushes or v*.*.* tags — never on feature branches.
            "if": ("github.event_name == 'push' && "
                   "(github.ref == 'refs/heads/main' || "
                   "startsWith(github.ref, 'refs/tags/v'))"),
            "defaults": {"run": {"working-directory": tf_root}},
            "steps": [
                checkout,
                cloud_auth,
                setup_terraform,
                {"name": "Download tfplan artifact",
                 "uses": "actions/download-artifact@v4",
                 "with": {"name": "tfplan", "path": tf_root}},
                {"name": "terraform init",
                 "run": f"terraform init -input=false -backend-config=key={backend_key}"},
                {"name": "terraform apply (from artifact)",
                 "run": "terraform apply -input=false -auto-approve tfplan"},
                {"name": "terraform output",
                 "run": "terraform output -json > outputs.json"},
                {"name": "Upload terraform outputs",
                 "uses": "actions/upload-artifact@v4",
                 "with": {"name": "terraform-outputs",
                          "path": f"{tf_root}/outputs.json",
                          "retention-days": 90}},
            ],
        }

        wf = {
            "name": f"AIPP Terraform - {self.repo_name}",
            "on": {
                "push": {"branches": ["develop", "release/*", "main"],
                         "tags": ["v*.*.*"]},
                "pull_request": {"branches": ["develop", "main"]},
                "workflow_dispatch": {},
            },
            "permissions": {"contents": "read", "id-token": "write"},
            "jobs": {
                "validate": validate_job,
                "plan":     plan_job,
                "policy":   policy_job,
                "apply":    apply_job,
            },
        }
        rendered = yaml.safe_dump(wf, sort_keys=False, width=140)

        # Inject `#` comments above each job + key step so a human reading
        # the workflow file understands the flow at a glance.
        from backend.generators.base import inject_comments
        header = (
            f"# ==================================================================\n"
            f"#  AIPP-generated Terraform infra workflow · {provider_note}\n"
            f"#  Uses HashiCorp's official `hashicorp/setup-terraform@v3` action\n"
            f"#  plus community-standard actions for tflint / tfsec / conftest.\n"
            f"#  Flow: validate → plan → policy → apply (manual approval).\n"
            f"# ==================================================================\n"
        )
        commented = inject_comments(rendered, {
            "validate:":
                ["-----------------------------------------------------------",
                 "JOB 1 · VALIDATE",
                 "fmt + init + validate + tflint + tfsec (offline gates only)",
                 "-----------------------------------------------------------"],
            "plan:":
                ["-----------------------------------------------------------",
                 "JOB 2 · PLAN — produces `tfplan` artifact for apply stage",
                 "-----------------------------------------------------------"],
            "policy:":
                ["-----------------------------------------------------------",
                 "JOB 3 · POLICY — OPA/conftest + optional Terratest (soft-fail)",
                 "-----------------------------------------------------------"],
            "apply:":
                ["-----------------------------------------------------------",
                 "JOB 4 · APPLY — manual-approval `environment: production`",
                 "Runs only on main or v*.*.* tags. Consumes tfplan artifact.",
                 "-----------------------------------------------------------"],
        })
        return header + commented
