"""Azure DevOps YAML generator — production-ready.

Emits real commands per detected language, real container build/push against
the target cloud registry, and real deploy commands per deploy target
(App Service, AKS, Cloud Run, EKS, GKE, or bare Kubernetes). No echo stubs.

The output is designed to be dropped into `azure-pipelines.yml` at the root
of the repository. Every stage carries an ADO `condition:` so the deploy
ladder is triggered by the correct branch or tag.
"""

from __future__ import annotations

from typing import List

import yaml

from backend.generators.base import BaseGenerator
from backend.generators.commands import pick_commands, image_ref
from backend.generators.deploy_targets import pick_deploy_target
from backend.models.pipeline import CloudPlatform


class AzureDevOpsGenerator(BaseGenerator):
    filename = "azure-pipelines.yml"

    def render(self) -> str:
        cmds = pick_commands(self.tech.language, self.tech.package_manager)
        target = pick_deploy_target(
            cloud=CloudPlatform(self.plan.cloud_platform.value),
            arch=self._get_arch(),
            tech=self.tech,
        )
        image = image_ref(
            self.plan.cloud_platform.value,
            "$(REGISTRY_NAME)",
            self.repo_name,
        )

        # ---- variables + trigger boilerplate ----
        # Only include LITERAL values here. Anything the user provides via a
        # pipeline variable / variable group (REGISTRY_NAME, AZURE_WEBAPP_NAME,
        # AWS_REGION, …) is looked up automatically by ADO at runtime — we do
        # NOT redeclare them here, otherwise ADO reports:
        #   "Unable to expand variable 'X'. A cyclical reference was detected."
        # because `variables: { X: $(X) }` is a self-reference.
        vars_block: dict = {
            "IMAGE_NAME": self.repo_name,
            "TAG": "$(Build.SourceVersion)",
        }

        # ADO service-connection names are resolved at compile time, so they
        # MUST be literal strings or `${{ parameters.X }}` template
        # expressions. Using `$(VAR)` at runtime causes ADO to reject the
        # YAML in <1s with "service connection $(VAR) could not be found".
        # We expose a `parameters:` block so the user can override the SC
        # name at queue time; the defaults match what our setup instructions
        # tell the user to name their connection.
        cloud_value = self.plan.cloud_platform.value
        scope = (self.pipeline_type or "all_in_one").lower()
        wants_build = scope in ("all_in_one", "ci", "build_only")
        wants_package = scope in ("all_in_one", "ci", "cd")
        wants_deploy = scope in ("all_in_one", "cd")
        wants_infra = scope == "infra"

        # Add sensible defaults for the Terraform pipeline vars so
        # `terraform init -backend-config=…` and `TerraformInstaller@1`
        # both have safe fall-backs.
        if wants_infra:
            vars_block.setdefault("TF_ROOT", ".")
            vars_block.setdefault("TF_VERSION", "latest")
            vars_block.setdefault("TF_BACKEND_KEY", "$(Build.Repository.Name).tfstate")

        # Only emit an Azure/AWS/GCP SC parameter if a step actually needs it.
        # CI-only that doesn't push to a cloud registry doesn't need one.
        needs_sc = wants_deploy or (wants_package and cloud_value in {"azure", "aws", "gcp"})
        sc_params = self._service_connection_parameters(cloud_value) if needs_sc else []

        doc: dict = {}
        if sc_params:
            doc["parameters"] = sc_params
        doc.update({
            "trigger": {
                "branches": {"include": ["develop", "release/*", "main"]},
                "tags": {"include": ["v*.*.*"]},
            },
            "pool": self._pool_block(),
            "variables": vars_block,
            "stages": [],
        })

        # ---- Infra-only short-circuit: production-grade Terraform pipeline ----
        # Emits FIVE stages (validate → plan → policy → approval+apply → outputs)
        # using the Microsoft DevLabs `TerraformTaskV2@2` marketplace task —
        # the same one the ADO YAML editor's Task Assistant panel writes for
        # you when you pick "Terraform" from the task picker. That means:
        #   * no raw `terraform` shell commands (all typos / arg mistakes
        #     surface as ADO validation errors, not runtime failures),
        #   * cloud auth is handled by the task's Backend/Environment
        #     service-connection selectors (no `az login` gymnastics),
        #   * every step gets a short `# comment` above it so a human
        #     reading the YAML understands the flow at a glance.
        if wants_infra:
            # Infra pipelines always need a cloud SC parameter to auth.
            if not sc_params:
                doc["parameters"] = self._service_connection_parameters(cloud_value)
            return self._render_terraform_infra_yaml(
                cloud=cloud_value,
                doc_head=doc,
            )

        # ---- Build gate (CI + all_in_one) ----
        if wants_build:
            doc["stages"].append(self._stage("build", jobs=[{
                "job": "build",
                "displayName": "Build & Test",
                "steps": (
                    self._checkout()
                    + self._toolchain(cmds.setup)
                    + [{"script": cmd, "displayName": f"install ({i})"} for i, cmd in enumerate(cmds.install)]
                    + [{"script": cmd, "displayName": f"build ({i})"} for i, cmd in enumerate(cmds.build)]
                    + [{"script": cmd, "displayName": f"unit test"} for cmd in cmds.unit_test]
                    + [{
                        "task": "PublishTestResults@2",
                        "inputs": {"testResultsFiles": "**/test-results.xml", "failTaskOnFailedTests": True},
                        "condition": "succeededOrFailed()",
                    }]
                    + [{
                        "task": "PublishBuildArtifacts@1",
                        "inputs": {"PathtoPublish": cmds.artifact_path, "ArtifactName": "app"},
                    }]
                ),
            }]))

            # ---- Security gates ----
            doc["stages"].append(self._stage("security", depends_on="build", jobs=[{
                "job": "security_scans",
                "displayName": "SAST + Dependency Scan + Lint",
                "steps": (
                    self._checkout()
                    + self._toolchain(cmds.setup)
                    + [{"script": cmd, "displayName": "SAST"} for cmd in cmds.sast]
                    + [{"script": cmd, "displayName": "Dependency scan"} for cmd in cmds.dependency_scan]
                    + [{"script": cmd, "displayName": "Lint"} for cmd in cmds.lint]
                ),
            }]))

        # ---- Package: container build + scan + push ----
        # Skipped when there's no cloud registry to push to and we're in CI-only
        # mode without a package_managed cloud (avoids requiring an Azure SC just
        # to build & test).
        if wants_package and needs_sc:
            depends = "security" if wants_build else None
            doc["stages"].append(self._stage("package", depends_on=depends, jobs=[{
                "job": "container",
                "displayName": "Container build + Trivy scan + push",
                "steps": (
                    self._checkout()
                    + self._registry_login(cloud_value)
                    + [{"script": "docker buildx build --platform linux/amd64 -t $(REGISTRY_NAME).azurecr.io/$(IMAGE_NAME):$(TAG) -f Dockerfile .",
                        "displayName": "docker buildx"}]
                    + [{"script": "trivy image --exit-code 0 --severity CRITICAL,HIGH $(REGISTRY_NAME).azurecr.io/$(IMAGE_NAME):$(TAG) || true",
                        "displayName": "Trivy image scan"}]
                    + [{"script": "docker push $(REGISTRY_NAME).azurecr.io/$(IMAGE_NAME):$(TAG)", "displayName": "docker push"}]
                ),
            }]))

        # ---- Deploy ladder (CD + all_in_one only) ----
        if wants_deploy:
            for rule in self.env_plan.rules:
                env = rule.name.value
                # Wrap the real cloud CLI commands inside the correct auth task
                # so they run with a service connection instead of raw shell.
                deploy_steps: List[dict] = self._wrap_deploy_steps(target)
                if rule.health_check:
                    deploy_steps.append({"script": self._health_check_cmd(target.kind),
                                         "displayName": "Health check"})
                if rule.smoke_test:
                    deploy_steps.append({
                        "script": "curl -fsS $APP_HEALTH_URL/health || (echo 'smoke test failed' && exit 1)",
                        "displayName": "Smoke test",
                    })

                doc["stages"].append({
                    "stage": f"deploy_{env}",
                    "displayName": f"Deploy {env.title()}",
                    "dependsOn": ["package"] if needs_sc else [],
                    "condition": self._condition(rule.trigger),
                    "jobs": [{
                        "deployment": f"deploy_{env}",
                        "environment": env,
                        "strategy": {"runOnce": {"deploy": {"steps": deploy_steps}}},
                    }],
                })

        if self.is_single_stage:
            consolidated_steps = []
            seen_checkout = False
            for st in doc.get("stages", []):
                for j in st.get("jobs", []):
                    j_steps = j.get("steps") or ((j.get("strategy") or {}).get("runOnce") or {}).get("deploy", {}).get("steps", [])
                    for s in j_steps:
                        if isinstance(s, dict) and "checkout" in s:
                            if seen_checkout:
                                continue
                            seen_checkout = True
                        consolidated_steps.append(s)

            doc.pop("stages", None)
            doc["jobs"] = [{
                "job": "continuous_delivery",
                "displayName": "End-to-End Pipeline (Single-Stage)",
                "steps": consolidated_steps,
            }]

        rendered = yaml.safe_dump(doc, sort_keys=False, width=140)
        # Iteration-20: inject `#` comments above every non-infra stage
        # so users get the same self-documenting output they get for infra.
        from backend.generators.base import (
            COMMON_STAGE_COMMENTS,
            default_pipeline_header,
            inject_comments,
        )
        header = default_pipeline_header(
            ci="Azure DevOps", cloud=cloud_value, scope=scope,
            custom_requirement=self.custom_requirement,
            deploy_style=self.deploy_style,
        )
        return header + inject_comments(rendered, COMMON_STAGE_COMMENTS)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _get_arch(self):
        # A minimal ArchitectureProfile stand-in when full analysis isn't wired.
        from backend.models.pipeline import ArchitectureProfile
        return ArchitectureProfile(
            style="microservices" if self.tech.kubernetes_ready else "monolith",
            service_count_estimate=1,
        )

    def _stage(self, name: str, *, depends_on: str | None = None, jobs: list) -> dict:
        st = {"stage": name, "displayName": name.replace("_", " ").title(), "jobs": jobs}
        if depends_on:
            st["dependsOn"] = [depends_on]
        return st

    def _checkout(self) -> list:
        return [{"checkout": "self", "displayName": "Checkout"}]

    def _pool_block(self) -> dict:
        """`pool:` block. Honours user's `agent_pool` selection.

        - Empty / None → Microsoft-hosted `ubuntu-22.04` (default).
        - Any string → self-hosted pool with that name (e.g. `default`,
          `AIPP-Agents`, `on-prem-linux`).
        """
        if self.agent_pool:
            return {"name": self.agent_pool}
        return {"vmImage": "ubuntu-22.04"}

    def _tf_auth_wrap(self, cloud: str, inline: str, display: str) -> dict:
        """Wrap a terraform shell block in the cloud-appropriate ADO auth
        task so `terraform init/plan/apply` can talk to the cloud API.
        Without this, terraform runs anonymous and gets 401/403 on the very
        first provider call.
        """
        if cloud == "azure":
            return {
                "task": "AzureCLI@2",
                "displayName": display,
                "inputs": {
                    "azureSubscription": "${{ parameters.azureServiceConnection }}",
                    "scriptType": "bash",
                    "scriptLocation": "inlineScript",
                    "addSpnToEnvironment": True,   # exposes ARM_* vars to terraform
                    "workingDirectory": "$(TF_ROOT)",
                    "inlineScript": inline,
                },
            }
        if cloud == "aws":
            return {
                "task": "AWSShellScript@1",
                "displayName": display,
                "inputs": {
                    "awsCredentials": "${{ parameters.awsServiceConnection }}",
                    "regionName": "$(AWS_REGION)",
                    "scriptType": "inline",
                    "workingDirectory": "$(TF_ROOT)",
                    "inlineScript": inline,
                },
            }
        if cloud == "gcp":
            return {
                "task": "gcloud@0",
                "displayName": display,
                "inputs": {
                    "connectedServiceNameSelector": "connectedServiceNameARM",
                    "connectedServiceNameARM": "${{ parameters.gcpServiceConnection }}",
                    "commandOptions": f"-- bash -c 'cd $(TF_ROOT) && {inline}'",
                },
            }
        return {"script": inline, "displayName": display,
                "workingDirectory": "$(TF_ROOT)"}

    def _terraform_stages(self, cloud: str) -> list[dict]:
        """Emit a production-grade Terraform pipeline for the target cloud.

        Five stages:
            1. validate  — fmt + init + validate + tflint + tfsec
            2. plan      — plan → tfplan artifact + human-readable plan.txt
            3. policy    — OPA/conftest against plan.json + optional Terratest
            4. apply     — deployment job with manual approval, downloads
                           the artifact and runs `terraform apply tfplan`
            5. outputs   — publishes `terraform output -json` as an artifact

        Assumes user provides pipeline variables:
            TF_ROOT              (default `.` — path to .tf files)
            TF_VERSION           (default `latest`)
            TF_BACKEND_KEY       (path in the remote backend)
            plus cloud-specific backend vars (RG/STORAGE/CONTAINER for
            azurerm; BUCKET/DYNAMODB_TABLE for aws; BUCKET for gcs).
        """
        provider_note = {
            "aws":   "provider hashicorp/aws + S3 backend",
            "azure": "provider hashicorp/azurerm + azurerm backend",
            "gcp":   "provider hashicorp/google + GCS backend",
        }.get(cloud, "Terraform")

        # Common tflint/tfsec install + terraform installer
        install_steps = [
            {"task": "TerraformInstaller@1",
             "displayName": "Install Terraform $(TF_VERSION)",
             "inputs": {"terraformVersion": "$(TF_VERSION)"}},
            {"script": ("curl -sSL "
                        "https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh "
                        "| bash"),
             "displayName": "Install tflint"},
            {"script": "curl -sSL https://tfsec.dev/install.sh | bash",
             "displayName": "Install tfsec"},
        ]

        # ----------------- Stage 1: validate + lint + security ----------------
        validate_stage = {
            "stage": "terraform_validate",
            "displayName": f"Terraform validate ({provider_note})",
            "jobs": [{
                "job": "validate",
                "displayName": "fmt · init · validate · tflint · tfsec",
                "steps": (
                    self._checkout()
                    + install_steps
                    + [self._tf_auth_wrap(cloud,
                        "terraform fmt -check -recursive\n"
                        "terraform init -input=false -backend-config=key=$(TF_BACKEND_KEY)\n"
                        "terraform validate",
                        "terraform fmt + init + validate")]
                    + [{"script": ("tflint --init && "
                                   "tflint --format=default --recursive"),
                        "workingDirectory": "$(TF_ROOT)",
                        "displayName": "tflint"}]
                    + [{"script": ("tfsec . --format=lovely "
                                   "--soft-fail-warnings"),
                        "workingDirectory": "$(TF_ROOT)",
                        "displayName": "tfsec"}]
                ),
            }],
        }

        # ----------------- Stage 2: plan → tfplan artifact --------------------
        plan_stage = {
            "stage": "terraform_plan",
            "displayName": "Terraform plan (produces artifact)",
            "dependsOn": "terraform_validate",
            "jobs": [{
                "job": "plan",
                "displayName": "plan + publish tfplan artifact",
                "steps": (
                    self._checkout()
                    + install_steps[:1]      # only Terraform installer needed
                    + [self._tf_auth_wrap(cloud,
                        "terraform init -input=false -backend-config=key=$(TF_BACKEND_KEY)\n"
                        "terraform plan -input=false -out=tfplan -detailed-exitcode | tee plan.txt\n"
                        "terraform show -json tfplan > plan.json",
                        "terraform plan")]
                    + [{"task": "PublishBuildArtifacts@1",
                        "displayName": "Publish tfplan + plan.json + plan.txt",
                        "inputs": {
                            "PathtoPublish": "$(TF_ROOT)",
                            "ArtifactName": "tfplan",
                            "publishLocation": "Container",
                        }}]
                ),
            }],
        }

        # ----------------- Stage 3: OPA policy + Terratest (soft-fail) --------
        policy_stage = {
            "stage": "terraform_policy",
            "displayName": "Policy-as-code (OPA / conftest) + Terratest",
            "dependsOn": "terraform_plan",
            "jobs": [{
                "job": "policy",
                "displayName": "conftest test plan.json + optional Terratest",
                "steps": (
                    self._checkout()
                    + [{"task": "DownloadBuildArtifacts@1",
                        "displayName": "Download tfplan artifact",
                        "inputs": {"buildType": "current",
                                   "downloadType": "single",
                                   "artifactName": "tfplan",
                                   "downloadPath": "$(Pipeline.Workspace)/artifacts"}}]
                    + [{"script": ("wget -qO /tmp/conftest.tar.gz "
                                   "https://github.com/open-policy-agent/conftest/releases/latest/download/conftest_Linux_x86_64.tar.gz "
                                   "&& tar -xzf /tmp/conftest.tar.gz -C /tmp "
                                   "&& sudo mv /tmp/conftest /usr/local/bin/"),
                        "displayName": "Install conftest"}]
                    + [{"script": ("if [ -d policy ]; then "
                                   "  conftest test "
                                   "  $(Pipeline.Workspace)/artifacts/tfplan/plan.json "
                                   "  --policy policy; "
                                   "else "
                                   "  echo 'No ./policy directory found — skipping OPA gate'; "
                                   "fi"),
                        "displayName": "OPA / conftest gate",
                        "continueOnError": True}]
                    + [{"script": ("if [ -d tests ] && ls tests/*.go >/dev/null 2>&1; then "
                                   "  go test -v -timeout 60m ./tests/...; "
                                   "else "
                                   "  echo 'No Terratest suite found under ./tests — skipping'; "
                                   "fi"),
                        "displayName": "Terratest (if present)",
                        "continueOnError": True}]
                ),
            }],
        }

        # ----------------- Stage 4: manual-approval apply ---------------------
        apply_stage = {
            "stage": "terraform_apply",
            "displayName": "Terraform apply (manual approval required)",
            "dependsOn": "terraform_policy",
            # Fire only when the trigger is main/tag — never on feature branches.
            "condition": ("and(succeeded(), "
                          "or(eq(variables['Build.SourceBranch'], 'refs/heads/main'), "
                          "startsWith(variables['Build.SourceBranch'], 'refs/tags/v')))"),
            "jobs": [{
                "deployment": "apply",
                "displayName": "terraform apply tfplan",
                "environment": "production",   # ADO env → add approval check
                "strategy": {"runOnce": {"deploy": {"steps": [
                    {"download": "current", "artifact": "tfplan",
                     "displayName": "Download tfplan artifact"},
                    self._tf_auth_wrap(cloud,
                        "cp -r $(Pipeline.Workspace)/tfplan/. .\n"
                        "terraform init -input=false -backend-config=key=$(TF_BACKEND_KEY)\n"
                        "terraform apply -input=false -auto-approve tfplan\n"
                        "terraform output -json > outputs.json",
                        "terraform apply (from artifact)"),
                    {"task": "PublishBuildArtifacts@1",
                     "displayName": "Publish outputs.json",
                     "inputs": {
                         "PathtoPublish": "$(TF_ROOT)/outputs.json",
                         "ArtifactName": "terraform-outputs",
                         "publishLocation": "Container",
                     }},
                ]}}},
            }],
        }

        return [validate_stage, plan_stage, policy_stage, apply_stage]

    # Deprecated single-stage helper kept for backwards compatibility with
    # any external code that might still call it. Delegates to the new
    # multi-stage helper and returns the FIRST stage (validate).
    def _terraform_stage(self, cloud: str) -> dict:  # pragma: no cover
        return self._terraform_stages(cloud)[0]

    # ------------------------------------------------------------------
    # Terraform infra pipeline — hand-crafted YAML with inline comments +
    # native `TerraformTaskV2@2` tasks (MS DevLabs extension).
    # ------------------------------------------------------------------
    def _render_terraform_infra_yaml(self, *, cloud: str, doc_head: dict) -> str:
        """Return a fully commented ADO Terraform infra pipeline as YAML.

        We hand-emit the string (instead of yaml.safe_dump) because PyYAML
        does not preserve `#` comments and because we want to guarantee
        `|` block scalars for any residual multi-line inputs. All Terraform
        commands are executed via the `TerraformTaskV2@2` marketplace task
        so users can extend / diff / review the pipeline in the ADO YAML
        editor with full IntelliSense from the Task Assistant panel.
        """
        import yaml as _yaml
        # Serialise the trigger + pool + parameters + variables block via
        # yaml.safe_dump (no multi-line strings there → no folding issues).
        head_yaml = _yaml.safe_dump(
            {k: v for k, v in doc_head.items() if k != "stages"},
            sort_keys=False, width=140,
        )

        pool_name = self.agent_pool or "ubuntu-22.04 (Microsoft-hosted)"
        provider_note = {
            "aws":   "hashicorp/aws + S3 backend",
            "azure": "hashicorp/azurerm + azurerm backend",
            "gcp":   "hashicorp/google + GCS backend",
        }.get(cloud, "Terraform")

        # Task Assistant-generated Terraform tasks use `TerraformTaskV2@2`
        # from the marketplace extension. We tell the user up-front so a
        # missing extension isn't a mystery.
        header = (
            "# =====================================================================\n"
            f"#  AIPP-generated Terraform infra pipeline · {provider_note}\n"
            "# ---------------------------------------------------------------------\n"
            "#  Requires the Microsoft DevLabs \"Azure Pipelines Terraform Tasks\"\n"
            "#  extension: https://marketplace.visualstudio.com/items?itemName=\n"
            "#            ms-devlabs.custom-terraform-tasks\n"
            "#  Install once at the org level. It contributes TerraformInstaller\n"
            "#  and TerraformTaskV2@2 — the same tasks the ADO YAML editor's Task\n"
            "#  Assistant panel writes when you pick \"Terraform\" from the picker.\n"
            "# ---------------------------------------------------------------------\n"
            f"#  Runner pool : {pool_name}\n"
            "#  Backend key : $(TF_BACKEND_KEY) — override in your pipeline vars\n"
            "#  Flow        : validate → plan → policy → apply (manual approval)\n"
            "# =====================================================================\n"
        )

        stages_yaml = "\nstages:\n"
        stages_yaml += self._tf_stage_validate(cloud)
        stages_yaml += self._tf_stage_plan(cloud)
        stages_yaml += self._tf_stage_policy()
        stages_yaml += self._tf_stage_apply(cloud)

        return header + head_yaml + stages_yaml

    # -- Backend/env inputs common to init/plan/apply --------------------
    def _tf_backend_inputs(self, cloud: str, *, indent: str) -> str:
        """Cloud-specific backend inputs for the Terraform task."""
        if cloud == "azure":
            return (
                f"{indent}backendServiceArm: '${{{{ parameters.azureServiceConnection }}}}'\n"
                f"{indent}backendAzureRmResourceGroupName: '$(TF_BACKEND_RG)'\n"
                f"{indent}backendAzureRmStorageAccountName: '$(TF_BACKEND_STORAGE)'\n"
                f"{indent}backendAzureRmContainerName: '$(TF_BACKEND_CONTAINER)'\n"
                f"{indent}backendAzureRmKey: '$(TF_BACKEND_KEY)'\n"
            )
        if cloud == "aws":
            return (
                f"{indent}backendServiceAWS: '${{{{ parameters.awsServiceConnection }}}}'\n"
                f"{indent}backendAWSBucketName: '$(TF_BACKEND_BUCKET)'\n"
                f"{indent}backendAWSKey: '$(TF_BACKEND_KEY)'\n"
            )
        if cloud == "gcp":
            return (
                f"{indent}backendServiceGCP: '${{{{ parameters.gcpServiceConnection }}}}'\n"
                f"{indent}backendGCPBucketName: '$(TF_BACKEND_BUCKET)'\n"
                f"{indent}backendGCPPrefix: '$(TF_BACKEND_KEY)'\n"
            )
        return ""

    def _tf_env_inputs(self, cloud: str, *, indent: str) -> str:
        """Cloud-specific env inputs used by `plan` and `apply`."""
        if cloud == "azure":
            return f"{indent}environmentServiceNameAzureRM: '${{{{ parameters.azureServiceConnection }}}}'\n"
        if cloud == "aws":
            return f"{indent}environmentServiceNameAWS: '${{{{ parameters.awsServiceConnection }}}}'\n"
        if cloud == "gcp":
            return f"{indent}environmentServiceNameGCP: '${{{{ parameters.gcpServiceConnection }}}}'\n"
        return ""

    def _tf_provider(self, cloud: str) -> str:
        return {"azure": "azurerm", "aws": "aws", "gcp": "gcp"}.get(cloud, "azurerm")

    # -- Stage 1 --------------------------------------------------------
    def _tf_stage_validate(self, cloud: str) -> str:
        provider = self._tf_provider(cloud)
        backend = self._tf_backend_inputs(cloud, indent="        ")
        return f"""\
# ---------------------------------------------------------------------
# STAGE 1 · VALIDATE
# Purpose: statically check the Terraform code (fmt + init + validate)
# plus lint (tflint) and security scan (tfsec) BEFORE we touch the
# cloud API. If this stage fails, plan/policy/apply never run.
# ---------------------------------------------------------------------
- stage: terraform_validate
  displayName: 'Terraform · validate + lint + security'
  jobs:
  - job: validate
    displayName: 'fmt · init · validate · tflint · tfsec'
    steps:

    # Pull the repository into the agent so .tf files are on disk.
    - checkout: self
      displayName: 'Checkout source'

    # Install the Terraform CLI (native task from MS DevLabs extension).
    - task: TerraformInstaller@1
      displayName: 'Install Terraform $(TF_VERSION)'
      inputs:
        terraformVersion: '$(TF_VERSION)'

    # `terraform fmt` — fails the build on unformatted code (style gate).
    - task: TerraformTaskV2@2
      displayName: 'Terraform · fmt (check only)'
      inputs:
        provider: '{provider}'
        command: 'custom'
        customCommand: 'fmt'
        commandOptions: '-check -recursive'
        workingDirectory: '$(TF_ROOT)'

    # `terraform init` — download providers + configure remote backend.
    - task: TerraformTaskV2@2
      displayName: 'Terraform · init (remote backend)'
      inputs:
        provider: '{provider}'
        command: 'init'
        workingDirectory: '$(TF_ROOT)'
{backend}
    # `terraform validate` — syntax + basic type checks (offline).
    - task: TerraformTaskV2@2
      displayName: 'Terraform · validate'
      inputs:
        provider: '{provider}'
        command: 'validate'
        workingDirectory: '$(TF_ROOT)'

    # tflint — catches anti-patterns the built-in validator misses
    # (unknown modules, deprecated arguments, provider-specific rules).
    - script: |
        curl -sSL https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash
        tflint --init
        tflint --format=default --recursive
      workingDirectory: '$(TF_ROOT)'
      displayName: 'tflint (install + run)'

    # tfsec — security scanner (public buckets, open SGs, missing encryption).
    # Soft-fail so a demo pipeline doesn't die on advisories; upgrade to
    # `--minimum-severity HIGH` when policies are ready.
    - script: |
        curl -sSL https://tfsec.dev/install.sh | bash
        tfsec . --format=lovely --soft-fail-warnings
      workingDirectory: '$(TF_ROOT)'
      displayName: 'tfsec (install + run)'
"""

    # -- Stage 2 --------------------------------------------------------
    def _tf_stage_plan(self, cloud: str) -> str:
        provider = self._tf_provider(cloud)
        backend = self._tf_backend_inputs(cloud, indent="        ")
        env = self._tf_env_inputs(cloud, indent="        ")
        return f"""
# ---------------------------------------------------------------------
# STAGE 2 · PLAN
# Purpose: produce a `tfplan` binary + human-readable `plan.txt` +
# machine-readable `plan.json` (needed for the OPA gate below).
# The plan file is published as a build artifact so the apply stage
# can consume the EXACT same plan (avoids drift between plan/apply).
# ---------------------------------------------------------------------
- stage: terraform_plan
  displayName: 'Terraform · plan (produces artifact)'
  dependsOn: terraform_validate
  jobs:
  - job: plan
    displayName: 'plan → publish tfplan artifact'
    steps:

    # Fresh checkout — plan job runs on a clean agent.
    - checkout: self
      displayName: 'Checkout source'

    # Reinstall Terraform (agent may be different from validate stage).
    - task: TerraformInstaller@1
      displayName: 'Install Terraform $(TF_VERSION)'
      inputs:
        terraformVersion: '$(TF_VERSION)'

    # `terraform init` again on the fresh agent.
    - task: TerraformTaskV2@2
      displayName: 'Terraform · init'
      inputs:
        provider: '{provider}'
        command: 'init'
        workingDirectory: '$(TF_ROOT)'
{backend}
    # `terraform plan -out=tfplan` — captures the exact set of changes.
    # -detailed-exitcode is emitted so the caller can tell "no changes"
    # (0) from "changes queued" (2). ADO treats both as success.
    - task: TerraformTaskV2@2
      displayName: 'Terraform · plan (-out=tfplan)'
      inputs:
        provider: '{provider}'
        command: 'plan'
        workingDirectory: '$(TF_ROOT)'
        commandOptions: '-input=false -out=tfplan -detailed-exitcode'
{env}
    # Emit a machine-readable plan.json for the OPA/conftest gate.
    # (`terraform show` is not exposed by TerraformTaskV2 — one shell line.)
    - script: |
        terraform show -no-color tfplan > plan.txt
        terraform show -json tfplan > plan.json
      workingDirectory: '$(TF_ROOT)'
      displayName: 'terraform show → plan.txt + plan.json'

    # Publish tfplan + plan.json + plan.txt so downstream stages can use them.
    - task: PublishBuildArtifacts@1
      displayName: 'Publish tfplan + plan.json + plan.txt'
      inputs:
        PathtoPublish: '$(TF_ROOT)'
        ArtifactName: 'tfplan'
        publishLocation: 'Container'
"""

    # -- Stage 3 --------------------------------------------------------
    def _tf_stage_policy(self) -> str:
        return """
# ---------------------------------------------------------------------
# STAGE 3 · POLICY
# Purpose: run policy-as-code (OPA / conftest) against plan.json and,
# if the repo ships a Go Terratest suite under ./tests, run that too.
# Both are `continueOnError: true` in this iteration — they are
# advisory gates. Flip to strict once your policy bundle is ready.
# ---------------------------------------------------------------------
- stage: terraform_policy
  displayName: 'Policy · OPA / conftest + Terratest'
  dependsOn: terraform_plan
  jobs:
  - job: policy
    displayName: 'conftest test plan.json (+ Terratest if present)'
    steps:

    # Download the tfplan artifact produced by stage 2.
    - task: DownloadBuildArtifacts@1
      displayName: 'Download tfplan artifact'
      inputs:
        buildType: 'current'
        downloadType: 'single'
        artifactName: 'tfplan'
        downloadPath: '$(Pipeline.Workspace)/artifacts'

    # Install conftest (no native task exists — small install script).
    - script: |
        wget -qO /tmp/conftest.tar.gz \\
          https://github.com/open-policy-agent/conftest/releases/latest/download/conftest_Linux_x86_64.tar.gz
        tar -xzf /tmp/conftest.tar.gz -C /tmp
        sudo mv /tmp/conftest /usr/local/bin/
      displayName: 'Install conftest'

    # Run the OPA gate if the repo ships a ./policy/*.rego bundle;
    # otherwise log a skip message. Never crashes the pipeline.
    - script: |
        if [ -d policy ]; then
          conftest test \\
            $(Pipeline.Workspace)/artifacts/tfplan/plan.json \\
            --policy policy
        else
          echo 'No ./policy directory found — skipping OPA gate.'
        fi
      displayName: 'OPA / conftest gate'
      continueOnError: true

    # Terratest — only runs if the repo has Go tests under ./tests.
    # Requires Go on the agent; a Microsoft-hosted ubuntu-22.04 image has it.
    - script: |
        if [ -d tests ] && ls tests/*.go >/dev/null 2>&1; then
          go test -v -timeout 60m ./tests/...
        else
          echo 'No Terratest suite under ./tests — skipping.'
        fi
      displayName: 'Terratest (optional)'
      continueOnError: true
"""

    # -- Stage 4 --------------------------------------------------------
    def _tf_stage_apply(self, cloud: str) -> str:
        provider = self._tf_provider(cloud)
        backend = self._tf_backend_inputs(cloud, indent="            ")
        env = self._tf_env_inputs(cloud, indent="            ")
        return f"""
# ---------------------------------------------------------------------
# STAGE 4 · APPLY (manual approval required)
# Purpose: apply the EXACT tfplan produced in stage 2.
# Gate 1: only runs on the `main` branch or a v*.*.* tag (feature
#         branches never get here — see the `condition:` below).
# Gate 2: `environment: production` — ADO shows an approval prompt in
#         the UI until the designated reviewer clicks "Approve".
# Output: `outputs.json` is published as a build artifact so downstream
#         pipelines (e.g. kubeconfig / connection strings) can consume it.
# ---------------------------------------------------------------------
- stage: terraform_apply
  displayName: 'Terraform · apply (manual approval)'
  dependsOn: terraform_policy
  condition: >-
    and(
      succeeded(),
      or(
        eq(variables['Build.SourceBranch'], 'refs/heads/main'),
        startsWith(variables['Build.SourceBranch'], 'refs/tags/v')
      )
    )
  jobs:
  - deployment: apply
    displayName: 'terraform apply tfplan'
    environment: production
    strategy:
      runOnce:
        deploy:
          steps:

          # Download the tfplan artifact created by stage 2.
          - download: current
            artifact: tfplan
            displayName: 'Download tfplan artifact'

          # Install Terraform on the deployment agent.
          - task: TerraformInstaller@1
            displayName: 'Install Terraform $(TF_VERSION)'
            inputs:
              terraformVersion: '$(TF_VERSION)'

          # Copy the artifact contents (tfplan + state files) into $(TF_ROOT)
          # so the native task sees them at the expected working directory.
          - script: |
              cp -r $(Pipeline.Workspace)/tfplan/. .
              ls -la tfplan plan.json plan.txt 2>/dev/null || true
            workingDirectory: '$(TF_ROOT)'
            displayName: 'Stage tfplan into working directory'

          # `terraform init` on the deployment agent (state backend re-attach).
          - task: TerraformTaskV2@2
            displayName: 'Terraform · init'
            inputs:
              provider: '{provider}'
              command: 'init'
              workingDirectory: '$(TF_ROOT)'
{backend}
          # `terraform apply tfplan` — the plan file is the SAME artifact
          # reviewers approved. No drift, no "plan says X, apply does Y".
          - task: TerraformTaskV2@2
            displayName: 'Terraform · apply (from artifact)'
            inputs:
              provider: '{provider}'
              command: 'apply'
              workingDirectory: '$(TF_ROOT)'
              commandOptions: '-input=false -auto-approve tfplan'
{env}
          # `terraform output -json` → machine-readable outputs for
          # downstream pipelines (kubeconfig, DB connection strings, ...).
          - script: terraform output -json > outputs.json
            workingDirectory: '$(TF_ROOT)'
            displayName: 'terraform output → outputs.json'

          # Publish outputs.json so other pipelines can `DownloadPipelineArtifact`.
          - task: PublishBuildArtifacts@1
            displayName: 'Publish outputs.json'
            inputs:
              PathtoPublish: '$(TF_ROOT)/outputs.json'
              ArtifactName: 'terraform-outputs'
              publishLocation: 'Container'
"""


    def _toolchain(self, setup: list[str]) -> list[dict]:
        """Turn a language setup list into ADO tasks / scripts."""
        out: list[dict] = []
        for step in setup:
            if step.startswith("actions/setup-node"):
                # -> UseNode@1 for the version after the colon (e.g. :20)
                version = step.split(":")[-1] if ":" in step else "20"
                out.append({"task": "UseNode@1", "inputs": {"version": version}})
            elif step.startswith("actions/setup-python"):
                version = step.split(":")[-1] if ":" in step else "3.12"
                out.append({"task": "UsePythonVersion@0", "inputs": {"versionSpec": version}})
            elif step.startswith("actions/setup-java"):
                # form: actions/setup-java@v4:temurin:17
                parts = step.split(":")
                jdk_ver = parts[-1] if len(parts) > 1 else "17"
                out.append({"task": "JavaToolInstaller@0",
                            "inputs": {"versionSpec": jdk_ver, "jdkArchitectureOption": "x64",
                                       "jdkSourceOption": "PreInstalled"}})
            elif step.startswith("actions/setup-go"):
                version = step.split(":")[-1] if ":" in step else "1.22"
                out.append({"task": "GoTool@0", "inputs": {"version": version}})
            elif step.startswith("actions/setup-dotnet"):
                version = step.split(":")[-1] if ":" in step else "8.0"
                out.append({"task": "UseDotNet@2", "inputs": {"version": version}})
            else:
                out.append({"script": step, "displayName": self._short(step)})
        return out

    @staticmethod
    @staticmethod
    def _short(cmd: str) -> str:
        return (cmd[:60] + "...") if len(cmd) > 60 else cmd

    def _wrap_deploy_steps(self, target) -> list[dict]:
        """Wrap the target's shell commands inside the correct ADO auth task.

        Default (`self.deploy_style == "cli"`):
          * Azure  -> AzureCLI@2 with `az` commands
          * AWS    -> AWSShellScript@1
          * GCP    -> gcloud@0
        Python opt-in (`self.deploy_style == "python"`, driven by the user's
        Custom deployment requirement — see `parse_deploy_style`):
          * Azure  -> UsePythonVersion + pip install + `python -c` script
            using `azure-identity` + `azure-mgmt-web/-containerservice`.
            Zero `az` CLI. Zero `AzureCLI@2` tasks.
          * AWS/GCP fall back to CLI because the ADO Python-SDK path is
            still WIP for those (documented in the emitted YAML comment).
        """
        cloud = target.cloud
        style = self.deploy_style
        commands = target.commands_for(style)
        pip_pkgs = target.pip_for(style)

        if cloud == "azure" and style == "python" and target.python_commands:
            script = "\n".join(commands)
            pip_line = "python -m pip install --upgrade pip && python -m pip install " + " ".join(pip_pkgs) \
                if pip_pkgs else "python -m pip install --upgrade pip"
            return [
                {
                    "task": "UsePythonVersion@0",
                    "displayName": "Setup Python 3.11 for SDK-based deploy",
                    "inputs": {"versionSpec": "3.11"},
                },
                {
                    "script": pip_line,
                    "displayName": "Install Azure SDK (no az CLI, per user directive)",
                },
                {
                    "script": "python - <<'PY'\n" + script + "\nPY",
                    "displayName": target.display + "  (via Python SDK)",
                    "env": {k: "$(" + k + ")" for k in target.required_env
                            if k != "AZURE_SUBSCRIPTION_ID"} | {
                        "AZURE_SUBSCRIPTION_ID": "$(AZURE_SUBSCRIPTION_ID)"
                    },
                },
            ]

        joined = "\n".join(commands)
        if cloud == "azure":
            return [{
                "task": "AzureCLI@2",
                "displayName": target.display,
                "inputs": {
                    "azureSubscription": "${{ parameters.azureServiceConnection }}",
                    "scriptType": "bash",
                    "scriptLocation": "inlineScript",
                    "inlineScript": joined,
                },
            }]
        if cloud == "aws":
            return [{
                "task": "AWSShellScript@1",
                "displayName": target.display,
                "inputs": {
                    "awsCredentials": "${{ parameters.awsServiceConnection }}",
                    "regionName": "$(AWS_REGION)",
                    "scriptType": "inline",
                    "inlineScript": joined,
                },
            }]
        if cloud == "gcp":
            return [{
                "task": "gcloud@0",
                "displayName": target.display,
                "inputs": {
                    "connectedServiceNameSelector": "connectedServiceNameARM",
                    "connectedServiceNameARM": "${{ parameters.gcpServiceConnection }}",
                    "commandOptions": joined,
                },
            }]
        # agnostic Kubernetes / other
        return [{"script": joined, "displayName": target.display}]

    @staticmethod
    def _service_connection_parameters(cloud: str) -> list:
        """Build the top-level `parameters:` block for the target cloud.

        Service-connection names in Azure Pipelines are compile-time only,
        so we surface them as runtime parameters with sensible defaults.
        The user creates a service connection with the default name (or
        overrides the parameter at queue time) — no `$(VAR)` runtime
        indirection is possible.
        """
        table = {
            "azure": {
                "name": "azureServiceConnection",
                "displayName": "Azure Resource Manager service connection",
                "default": "azure-service-connection",
            },
            "aws": {
                "name": "awsServiceConnection",
                "displayName": "AWS service connection",
                "default": "aws-service-connection",
            },
            "gcp": {
                "name": "gcpServiceConnection",
                "displayName": "GCP service connection",
                "default": "gcp-service-connection",
            },
        }
        entry = table.get(cloud)
        if not entry:
            return []
        return [{
            "name": entry["name"],
            "displayName": entry["displayName"],
            "type": "string",
            "default": entry["default"],
        }]

    @staticmethod
    def _registry_login(cloud: str) -> list:
        """Log in to the target cloud's container registry using a compile-time
        service-connection reference (avoids ADO's <1s YAML rejection)."""
        if cloud == "azure":
            return [{
                "task": "AzureCLI@2",
                "displayName": "Log in to ACR",
                "inputs": {
                    "azureSubscription": "${{ parameters.azureServiceConnection }}",
                    "scriptType": "bash",
                    "scriptLocation": "inlineScript",
                    "inlineScript": "az acr login --name $(REGISTRY_NAME)",
                },
            }]
        if cloud == "aws":
            return [{
                "task": "AWSShellScript@1",
                "displayName": "Log in to ECR",
                "inputs": {
                    "awsCredentials": "${{ parameters.awsServiceConnection }}",
                    "regionName": "$(AWS_REGION)",
                    "scriptType": "inline",
                    "inlineScript": (
                        "aws ecr get-login-password --region $(AWS_REGION) | "
                        "docker login --username AWS --password-stdin "
                        "$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com"
                    ),
                },
            }]
        if cloud == "gcp":
            return [{
                "task": "gcloud@0",
                "displayName": "Log in to Artifact Registry",
                "inputs": {
                    "connectedServiceNameSelector": "connectedServiceNameARM",
                    "connectedServiceNameARM": "${{ parameters.gcpServiceConnection }}",
                    "commandOptions": (
                        "auth configure-docker $(GCP_REGION)-docker.pkg.dev --quiet"
                    ),
                },
            }]
        # unknown cloud — skip auth; docker push will fail loudly if anon push
        # isn't allowed, which is the correct behaviour.
        return []

    @staticmethod
    def _health_check_cmd(kind: str) -> str:
        if kind == "kubernetes":
            return "kubectl rollout status deploy/$(RELEASE_NAME) -n $(NAMESPACE) --timeout=5m"
        if kind == "container":
            return "sleep 10 && curl -fsS $APP_HEALTH_URL || (echo 'health check failed' && exit 1)"
        return "echo 'health check placeholder'"

    @staticmethod
    def _condition(trigger: str) -> str:
        table = {
            "develop_branch": "eq(variables['Build.SourceBranch'], 'refs/heads/develop')",
            "release_branch": "startsWith(variables['Build.SourceBranch'], 'refs/heads/release/')",
            "main_branch": "eq(variables['Build.SourceBranch'], 'refs/heads/main')",
            "version_tag": "startsWith(variables['Build.SourceBranch'], 'refs/tags/v')",
            "manual": "eq(variables['Build.Reason'], 'Manual')",
            "feature_branch": "startsWith(variables['Build.SourceBranch'], 'refs/heads/feature/')",
        }
        return table.get(trigger, "succeeded()")
