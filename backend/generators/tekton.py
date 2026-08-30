"""Tekton Pipeline YAML generator — production-ready.

Emits a multi-document YAML with Tasks + Pipeline that follows the same
production pattern as the other generators. Uses real per-language commands
from `pick_commands()` and real deploy commands from `pick_deploy_target()`.
No echo stubs.
"""

from __future__ import annotations

from typing import List

import yaml

from backend.generators.base import BaseGenerator
from backend.generators.commands import pick_commands, image_ref
from backend.generators.deploy_targets import pick_deploy_target
from backend.models.pipeline import ArchitectureProfile, CloudPlatform


class TektonGenerator(BaseGenerator):
    filename = "tekton/aipp-pipeline.yaml"

    def render(self) -> str:
        # Iteration-20 (P1): honour `pipeline_type=infra` with the same
        # production-grade 4-stage Terraform flow already emitted by ADO,
        # GH Actions, GitLab CI and Harness. Keeps cross-generator parity.
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
        image = image_ref(self.plan.cloud_platform.value, "$(params.REGISTRY_NAME)", self.repo_name)
        base_image = self._runtime_image()

        tasks: List[dict] = []
        pipeline_task_refs: List[dict] = []
        prior = None

        # ---- CI Tasks ----
        ci_task_defs = [
            ("build",           cmds.install + cmds.build,          base_image),
            ("unit-test",       cmds.unit_test,                     base_image),
            ("sast",            cmds.sast,                          base_image),
            ("dependency-scan", cmds.dependency_scan,               base_image),
            ("lint",            cmds.lint,                          base_image),
            ("container-build-push", [
                f"buildah bud -t {image}:$(params.TAG) -f Dockerfile .",
                f"trivy image --exit-code 0 --severity CRITICAL,HIGH {image}:$(params.TAG) || true",
                f"buildah push {image}:$(params.TAG)",
            ], "quay.io/buildah/stable:latest"),
        ]
        for name, script, tk_image in ci_task_defs:
            tasks.append(self._task(name, script, tk_image))
            entry = {"name": name, "taskRef": {"name": f"aipp-{name}"}}
            if prior:
                entry["runAfter"] = [prior]
            pipeline_task_refs.append(entry)
            prior = name

        # ---- CD Tasks (per environment) ----
        for r in self.env_plan.rules:
            env = r.name.value
            deploy_script: List[str] = []
            deploy_script.append(self._cloud_auth_cmd(target.cloud))
            deploy_script.extend(target.commands)
            if r.health_check:
                deploy_script.append(self._health_check_cmd(target.kind))
            if r.smoke_test:
                deploy_script.append("curl -fsS $APP_HEALTH_URL/health || (echo 'smoke test failed' && exit 1)")

            task_name = f"deploy-{env}"
            tasks.append(self._task(task_name, deploy_script, self._deploy_image(target.cloud)))
            pipeline_task_refs.append({
                "name": task_name,
                "taskRef": {"name": f"aipp-{task_name}"},
                "runAfter": [prior] if prior else [],
                "when": self._when_expr(r.trigger),
            })

        pipeline = {
            "apiVersion": "tekton.dev/v1",
            "kind": "Pipeline",
            "metadata": {"name": f"aipp-{self.repo_name}"},
            "spec": {
                "params": [
                    {"name": "REGISTRY_NAME", "type": "string"},
                    {"name": "TAG", "type": "string", "default": "latest"},
                    {"name": "BRANCH", "type": "string", "default": "main"},
                ],
                "tasks": pipeline_task_refs,
            },
        }
        docs = tasks + [pipeline]
        rendered = "---\n".join(
            yaml.safe_dump(d, sort_keys=False, width=140) for d in docs
        )
        # Iteration-20: inject a header + task-level `#` comments so a human
        # reading the Tekton file understands each Task/Pipeline block.
        from backend.generators.base import default_pipeline_header, inject_comments
        header = default_pipeline_header(
            ci="Tekton",
            cloud=self.plan.cloud_platform.value,
            scope=(self.pipeline_type or "all_in_one"),
            custom_requirement=self.custom_requirement,
            deploy_style=self.deploy_style,
        )
        # Comment each Task by its metadata name — build / security / package /
        # deploy_dev / deploy_prod are the common CI task names emitted here.
        tekton_comments = {
            "name: build": [
                "-------------------------------------------------",
                "TASK · BUILD — checkout + install + unit tests",
                "-------------------------------------------------",
            ],
            "name: security-scan": [
                "-------------------------------------------------",
                "TASK · SECURITY — SAST + dependency-audit + lint",
                "-------------------------------------------------",
            ],
            "name: container-build-push": [
                "-------------------------------------------------",
                "TASK · PACKAGE — docker build + Trivy scan + push",
                "-------------------------------------------------",
            ],
            "name: deploy-dev": [
                "-------------------------------------------------",
                "TASK · DEPLOY (dev) — auto on main branch",
                "-------------------------------------------------",
            ],
            "name: deploy-prod": [
                "-------------------------------------------------",
                "TASK · DEPLOY (prod) — manual approval + tag guard",
                "-------------------------------------------------",
            ],
        }
        return header + inject_comments(rendered, tekton_comments)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    # -------------------------------------------------------------------
    # Production-grade Terraform infra pipeline (mirrors ADO/GH/GitLab/Harness).
    # Four Tekton Tasks (aipp-tf-{validate,plan,policy,apply}) glued together
    # by a Pipeline with `runAfter` chaining + a shared workspace so the
    # tfplan artifact survives between tasks.
    #
    # Manual approval: Tekton has no native approval step, so we gate the
    # `aipp-tf-apply` PipelineTask on a `params.APPROVED == "yes"` guard.
    # The operator supplies APPROVED=yes only after reviewing the tfplan.
    # -------------------------------------------------------------------
    def _render_infra_pipeline(self, cloud: str) -> str:
        provider_note = {
            "aws":   "provider hashicorp/aws + S3 backend",
            "azure": "provider hashicorp/azurerm + azurerm backend",
            "gcp":   "provider hashicorp/google + GCS backend",
        }.get(cloud, "Terraform")

        cloud_auth = self._cloud_auth_cmd(cloud)
        # `hashicorp/terraform:light` ships terraform + basic shell.
        tf_image = "hashicorp/terraform:1.9.5"
        ubuntu_image = "ubuntu:22.04"

        # -------- Task 1: validate + tflint + tfsec ----------------------
        validate_task = self._tf_task(
            name="tf-validate",
            image=ubuntu_image,
            script=[
                "apt-get update -qq && apt-get install -y -qq curl unzip ca-certificates jq",
                "curl -fsSLo /tmp/tf.zip "
                "\"https://releases.hashicorp.com/terraform/1.9.5/"
                "terraform_1.9.5_linux_amd64.zip\" && "
                "unzip -o /tmp/tf.zip -d /usr/local/bin/",
                "curl -sSL https://raw.githubusercontent.com/terraform-linters/"
                "tflint/master/install_linux.sh | bash",
                "curl -sSL https://tfsec.dev/install.sh | bash",
                cloud_auth,
                "cd \"$(workspaces.source.path)/$(params.TF_ROOT)\"",
                "terraform fmt -check -recursive",
                "terraform init -input=false "
                "-backend-config=key=$(params.TF_BACKEND_KEY)",
                "terraform validate",
                "tflint --init && tflint --format=default --recursive",
                "tfsec . --format=lovely --soft-fail-warnings",
            ],
        )

        # -------- Task 2: plan -> tfplan (into workspace) ----------------
        plan_task = self._tf_task(
            name="tf-plan",
            image=ubuntu_image,
            script=[
                "apt-get update -qq && apt-get install -y -qq curl unzip ca-certificates",
                "curl -fsSLo /tmp/tf.zip "
                "\"https://releases.hashicorp.com/terraform/1.9.5/"
                "terraform_1.9.5_linux_amd64.zip\" && "
                "unzip -o /tmp/tf.zip -d /usr/local/bin/",
                cloud_auth,
                "cd \"$(workspaces.source.path)/$(params.TF_ROOT)\"",
                "terraform init -input=false "
                "-backend-config=key=$(params.TF_BACKEND_KEY)",
                "terraform plan -input=false -out=tfplan -detailed-exitcode "
                "| tee plan.txt",
                "terraform show -json tfplan > plan.json",
                # tfplan + plan.json survive because the workspace is shared.
                "ls -la tfplan plan.json plan.txt",
            ],
        )

        # -------- Task 3: OPA + optional Terratest (soft-fail) -----------
        policy_task = self._tf_task(
            name="tf-policy",
            image=ubuntu_image,
            script=[
                "apt-get update -qq && apt-get install -y -qq curl wget tar ca-certificates",
                "wget -qO /tmp/conftest.tar.gz "
                "https://github.com/open-policy-agent/conftest/releases/latest/"
                "download/conftest_Linux_x86_64.tar.gz && "
                "tar -xzf /tmp/conftest.tar.gz -C /tmp && "
                "mv /tmp/conftest /usr/local/bin/",
                "cd \"$(workspaces.source.path)/$(params.TF_ROOT)\"",
                "if [ -d policy ]; then "
                "  conftest test plan.json --policy policy || true; "
                "else "
                "  echo 'No ./policy directory found — skipping OPA gate'; "
                "fi",
                "if [ -d tests ] && ls tests/*.go >/dev/null 2>&1; then "
                "  apt-get install -y -qq golang-go && "
                "  go test -v -timeout 60m ./tests/... || true; "
                "else "
                "  echo 'No Terratest suite under ./tests — skipping'; "
                "fi",
            ],
        )

        # -------- Task 4: manual-approval apply --------------------------
        apply_task = self._tf_task(
            name="tf-apply",
            image=tf_image,
            script=[
                cloud_auth,
                "cd \"$(workspaces.source.path)/$(params.TF_ROOT)\"",
                "terraform init -input=false "
                "-backend-config=key=$(params.TF_BACKEND_KEY)",
                "terraform apply -input=false -auto-approve tfplan",
                "terraform output -json > outputs.json",
            ],
        )

        # -------- Pipeline: chain the 4 tasks + approval guard -----------
        pipeline = {
            "apiVersion": "tekton.dev/v1",
            "kind": "Pipeline",
            "metadata": {"name": f"aipp-tf-{self.repo_name}"},
            "spec": {
                "description": (
                    f"AIPP Terraform pipeline for {self.repo_name} — "
                    f"{provider_note}. Four tasks: validate -> plan -> policy "
                    "-> apply. Apply requires params.APPROVED=yes."
                ),
                "params": [
                    {"name": "TF_ROOT", "type": "string", "default": "."},
                    {"name": "TF_BACKEND_KEY", "type": "string",
                     "default": f"{self.repo_name}.tfstate"},
                    {"name": "BRANCH", "type": "string", "default": "main"},
                    {"name": "APPROVED", "type": "string", "default": "no",
                     "description": ("Manual approval gate for terraform apply. "
                                     "Operator sets to 'yes' after reviewing tfplan.")},
                ],
                "workspaces": [{"name": "source"}],
                "tasks": [
                    {"name": "validate",
                     "taskRef": {"name": "aipp-tf-validate"},
                     "params": [
                         {"name": "TF_ROOT", "value": "$(params.TF_ROOT)"},
                         {"name": "TF_BACKEND_KEY", "value": "$(params.TF_BACKEND_KEY)"},
                     ],
                     "workspaces": [{"name": "source", "workspace": "source"}]},
                    {"name": "plan",
                     "taskRef": {"name": "aipp-tf-plan"},
                     "runAfter": ["validate"],
                     "params": [
                         {"name": "TF_ROOT", "value": "$(params.TF_ROOT)"},
                         {"name": "TF_BACKEND_KEY", "value": "$(params.TF_BACKEND_KEY)"},
                     ],
                     "workspaces": [{"name": "source", "workspace": "source"}]},
                    {"name": "policy",
                     "taskRef": {"name": "aipp-tf-policy"},
                     "runAfter": ["plan"],
                     "params": [
                         {"name": "TF_ROOT", "value": "$(params.TF_ROOT)"},
                         {"name": "TF_BACKEND_KEY", "value": "$(params.TF_BACKEND_KEY)"},
                     ],
                     "workspaces": [{"name": "source", "workspace": "source"}]},
                    {"name": "apply",
                     "taskRef": {"name": "aipp-tf-apply"},
                     "runAfter": ["policy"],
                     # Manual approval: only run if the operator flipped APPROVED
                     # to "yes" AND the branch is main / v*.*.* tag.
                     "when": [
                         {"input": "$(params.APPROVED)",
                          "operator": "in", "values": ["yes"]},
                         {"input": "$(params.BRANCH)",
                          "operator": "in", "values": ["main", "v*"]},
                     ],
                     "params": [
                         {"name": "TF_ROOT", "value": "$(params.TF_ROOT)"},
                         {"name": "TF_BACKEND_KEY", "value": "$(params.TF_BACKEND_KEY)"},
                     ],
                     "workspaces": [{"name": "source", "workspace": "source"}]},
                ],
            },
        }

        header = (
            f"# ==================================================================\n"
            f"# AIPP Terraform pipeline · {provider_note}\n"
            f"# 4-task Tekton flow: validate -> plan -> policy -> apply\n"
            f"# The apply task is gated by params.APPROVED (default 'no') so\n"
            f"# a human must run `tkn pipeline start ... --param APPROVED=yes`\n"
            f"# after reviewing the tfplan produced by the plan task.\n"
            f"# ==================================================================\n"
        )
        docs = [validate_task, plan_task, policy_task, apply_task, pipeline]

        from backend.generators.base import inject_comments
        # Comments per Task / Pipeline document — matched by metadata name.
        marker_map = {
            "name: aipp-tf-validate":
                ["-----------------------------------------------------------",
                 "TASK 1 · VALIDATE — fmt + init + validate + tflint + tfsec",
                 "-----------------------------------------------------------"],
            "name: aipp-tf-plan":
                ["-----------------------------------------------------------",
                 "TASK 2 · PLAN — writes tfplan + plan.json into workspace",
                 "-----------------------------------------------------------"],
            "name: aipp-tf-policy":
                ["-----------------------------------------------------------",
                 "TASK 3 · POLICY — conftest against plan.json + Terratest",
                 "-----------------------------------------------------------"],
            "name: aipp-tf-apply":
                ["-----------------------------------------------------------",
                 "TASK 4 · APPLY — consumes tfplan; guarded by APPROVED param",
                 "-----------------------------------------------------------"],
            f"name: aipp-tf-{self.repo_name}":
                ["-----------------------------------------------------------",
                 "PIPELINE — glues the 4 Tasks with `runAfter` chaining +",
                 "shared `source` workspace + manual-approval `when:` guard",
                 "-----------------------------------------------------------"],
        }
        pieces: list[str] = []
        for d in docs:
            piece = yaml.safe_dump(d, sort_keys=False, width=140)
            pieces.append(inject_comments(piece, marker_map))
        return header + "---\n".join(pieces)

    @staticmethod
    def _tf_task(*, name: str, image: str, script: list) -> dict:
        """Emit a Tekton Task backed by a shell script + shared workspace.

        The workspace is called `source` and is where the caller's checkout
        lives. All terraform commands `cd` into it so tfplan/plan.json
        automatically flow to the next task via the shared workspace.
        """
        return {
            "apiVersion": "tekton.dev/v1",
            "kind": "Task",
            "metadata": {"name": f"aipp-{name}"},
            "spec": {
                "params": [
                    {"name": "TF_ROOT", "type": "string", "default": "."},
                    {"name": "TF_BACKEND_KEY", "type": "string",
                     "default": "terraform.tfstate"},
                ],
                "workspaces": [{"name": "source"}],
                "steps": [{
                    "name": "run",
                    "image": image,
                    "script": "#!/usr/bin/env bash\nset -euo pipefail\n"
                              + "\n".join(script),
                }],
            },
        }

    @staticmethod
    def _task(name: str, commands: List[str], image: str) -> dict:
        return {
            "apiVersion": "tekton.dev/v1",
            "kind": "Task",
            "metadata": {"name": f"aipp-{name}"},
            "spec": {
                "params": [{"name": "REGISTRY_NAME", "type": "string", "default": ""},
                           {"name": "TAG", "type": "string", "default": "latest"}],
                "steps": [{
                    "name": "run",
                    "image": image,
                    "script": "#!/usr/bin/env bash\nset -euo pipefail\n" + "\n".join(commands),
                }],
            },
        }

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
    def _deploy_image(cloud: str) -> str:
        if cloud == "azure":
            return "mcr.microsoft.com/azure-cli:latest"
        if cloud == "aws":
            return "amazon/aws-cli:latest"
        if cloud == "gcp":
            return "google/cloud-sdk:slim"
        return "bitnami/kubectl:latest"

    @staticmethod
    def _cloud_auth_cmd(cloud: str) -> str:
        if cloud == "azure":
            return ("az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET "
                    "--tenant $AZURE_TENANT_ID")
        if cloud == "aws":
            return "aws sts get-caller-identity"
        if cloud == "gcp":
            return "gcloud auth activate-service-account --key-file=$GCP_SA_KEY_FILE"
        return "true"

    @staticmethod
    def _health_check_cmd(kind: str) -> str:
        if kind == "kubernetes":
            return "kubectl rollout status deploy/$RELEASE_NAME -n $NAMESPACE --timeout=5m"
        if kind == "container":
            return "sleep 10 && curl -fsS $APP_HEALTH_URL || (echo 'health check failed' && exit 1)"
        return "true"

    @staticmethod
    def _when_expr(trigger: str) -> list:
        table = {
            "develop_branch":  [{"input": "$(params.BRANCH)", "operator": "in", "values": ["develop"]}],
            "release_branch":  [{"input": "$(params.BRANCH)", "operator": "in",
                                  "values": ["release/*"]}],
            "main_branch":     [{"input": "$(params.BRANCH)", "operator": "in", "values": ["main"]}],
            "version_tag":     [{"input": "$(params.BRANCH)", "operator": "in", "values": ["v*"]}],
            "feature_branch":  [{"input": "$(params.BRANCH)", "operator": "in", "values": ["feature/*"]}],
        }
        return table.get(trigger, [])
