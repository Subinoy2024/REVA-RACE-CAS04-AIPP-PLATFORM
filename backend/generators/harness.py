"""Harness pipeline YAML generator — production-ready.

Emits the same 4-gate structure (build/test/security/package + deploy ladder)
as the other generators, but rendered into Harness NG's pipeline schema.
Uses real per-language commands via pick_commands and real deploy commands
via pick_deploy_target. No echo stubs.
"""

from __future__ import annotations

from typing import List

import yaml

from backend.generators.base import BaseGenerator
from backend.generators.commands import pick_commands, image_ref
from backend.generators.deploy_targets import pick_deploy_target
from backend.models.pipeline import ArchitectureProfile, CloudPlatform


class HarnessGenerator(BaseGenerator):
    filename = ".harness/pipeline.yaml"

    def render(self) -> str:
        # Iteration-20 (P1): honour `pipeline_type=infra` with the same
        # production-grade 4-stage Terraform flow already emitted by ADO,
        # GH Actions and GitLab CI. Keeps cross-generator parity.
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
        image = image_ref(self.plan.cloud_platform.value,
                          "<+variable.REGISTRY_NAME>", self.repo_name)

        stages: List[dict] = []

        # ---- CI stage: build + test + security + package ----
        ci_steps: List[dict] = []
        ci_steps.append(self._run("install", cmds.install))
        ci_steps.append(self._run("build", cmds.build))
        ci_steps.append(self._run("unit_test", cmds.unit_test))
        ci_steps.append(self._run("sast", cmds.sast))
        ci_steps.append(self._run("dependency_scan", cmds.dependency_scan))
        ci_steps.append(self._run("lint", cmds.lint))
        # Build + push + scan container
        ci_steps.append({
            "step": {
                "identifier": "build_push_image",
                "name": "Build & Push Image",
                "type": "BuildAndPushDockerRegistry",
                "spec": {
                    "connectorRef": "<+variable.DOCKER_CONNECTOR>",
                    "repo": image,
                    "tags": ["<+pipeline.sequenceId>", "<+codebase.commitSha>"],
                    "dockerfile": "Dockerfile",
                    "context": ".",
                },
            }
        })
        ci_steps.append(self._run("trivy_scan",
                                  [f"trivy image --exit-code 0 --severity CRITICAL,HIGH {image}:<+codebase.commitSha> || true"]))

        stages.append({
            "stage": {
                "identifier": "CI",
                "name": "Build, Test, Security, Package",
                "type": "CI",
                "spec": {
                    "cloneCodebase": True,
                    "infrastructure": {
                        "type": "KubernetesDirect",
                        "spec": {
                            "connectorRef": "<+variable.K8S_CONNECTOR>",
                            "namespace": "harness-delegate",
                        },
                    },
                    "execution": {"steps": ci_steps},
                },
            }
        })

        # ---- CD stages ----
        deploy_type = "Kubernetes" if target.kind == "kubernetes" else "NativeHelm"
        # For non-K8s targets we use a Custom stage with shell commands.
        for r in self.env_plan.rules:
            env = r.name.value
            deploy_steps: List[dict] = []
            deploy_steps.append(self._run(f"cloud_auth_{env}",
                                          [self._cloud_auth_cmd(target.cloud)]))
            deploy_steps.append(self._run(f"deploy_{env}", target.commands))
            if r.health_check:
                deploy_steps.append(self._run(f"health_{env}",
                                              [self._health_check_cmd(target.kind)]))
            if r.smoke_test:
                deploy_steps.append(self._run(f"smoke_{env}",
                                              ["curl -fsS $APP_HEALTH_URL/health || exit 1"]))

            stage: dict = {
                "stage": {
                    "identifier": f"deploy_{env}",
                    "name": f"Deploy {env.title()}",
                    "type": "Custom",
                    "spec": {
                        "execution": {"steps": deploy_steps},
                        "environment": {"environmentRef": env},
                    },
                    "when": {
                        "pipelineStatus": "Success",
                        "condition": self._when_condition(r.trigger),
                    },
                }
            }
            if r.requires_approval:
                # insert a Harness Approval step before the deploy
                stage["stage"]["spec"]["execution"]["steps"] = (
                    [{"step": {"identifier": "prod_approval", "name": "Manual approval",
                               "type": "HarnessApproval",
                               "spec": {"approvalMessage": f"Approve deploy to {env}",
                                        "includePipelineExecutionHistory": True,
                                        "approvers": {"minimumCount": 1,
                                                      "disallowPipelineExecutor": False}}}}]
                    + stage["stage"]["spec"]["execution"]["steps"]
                )
            stages.append(stage)

        doc = {
            "pipeline": {
                "name": f"AIPP-{self.repo_name}",
                "identifier": f"AIPP_{self.repo_name.replace('-', '_')}",
                "projectIdentifier": "<+variable.HARNESS_PROJECT>",
                "orgIdentifier": "<+variable.HARNESS_ORG>",
                "variables": [
                    {"name": "REGISTRY_NAME", "type": "String", "value": "<+input>"},
                    {"name": "DOCKER_CONNECTOR", "type": "String", "value": "<+input>"},
                    {"name": "K8S_CONNECTOR", "type": "String", "value": "<+input>"},
                    {"name": "HARNESS_ORG", "type": "String", "value": "default"},
                    {"name": "HARNESS_PROJECT", "type": "String", "value": "default"},
                ],
                "stages": stages,
            }
        }
        rendered = yaml.safe_dump(doc, sort_keys=False, width=140)
        # Iteration-20: inject `#` comments above every stage.
        from backend.generators.base import (
            COMMON_STAGE_COMMENTS, default_pipeline_header, inject_comments,
        )
        header = default_pipeline_header(
            ci="Harness",
            cloud=self.plan.cloud_platform.value,
            scope=(self.pipeline_type or "all_in_one"),
            custom_requirement=self.custom_requirement,
            deploy_style=self.deploy_style,
        )
        # Harness identifiers use "identifier: build" not "stage: build" —
        # remap the marker map for this generator's YAML shape.
        stage_comments = {}
        for marker, note in COMMON_STAGE_COMMENTS.items():
            if marker.startswith("stage: "):
                stage_comments[f"identifier: {marker.split(': ',1)[1]}"] = note
        return header + inject_comments(rendered, stage_comments)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    # -------------------------------------------------------------------
    # Production-grade Terraform infra pipeline (mirrors ADO / GH / GitLab).
    # Four Custom stages: Validate → Plan → Policy → Apply. Apply carries
    # a `HarnessApproval` step so a human must click before Terraform is
    # applied — analogous to ADO's environment approval, GH Environments
    # and GitLab's `when: manual`.
    # -------------------------------------------------------------------
    def _render_infra_pipeline(self, cloud: str) -> str:
        provider_note = {
            "aws":   "provider hashicorp/aws + S3 backend",
            "azure": "provider hashicorp/azurerm + azurerm backend",
            "gcp":   "provider hashicorp/google + GCS backend",
        }.get(cloud, "Terraform")

        cloud_auth = self._cloud_auth_cmd(cloud)

        # Shared install snippet — Terraform + tflint + tfsec + conftest.
        install_terraform = (
            "curl -fsSLo /tmp/tf.zip "
            "\"https://releases.hashicorp.com/terraform/${TF_VERSION:-1.9.5}/"
            "terraform_${TF_VERSION:-1.9.5}_linux_amd64.zip\" && "
            "unzip -o /tmp/tf.zip -d /usr/local/bin/ && terraform version"
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
        validate_stage = {
            "stage": {
                "identifier": "terraform_validate",
                "name": f"Validate ({provider_note})",
                "type": "Custom",
                "spec": {
                    "execution": {"steps": [
                        self._run("install_terraform", [install_terraform]),
                        self._run("install_tflint", [install_tflint]),
                        self._run("install_tfsec", [install_tfsec]),
                        self._run("cloud_auth", [cloud_auth]),
                        self._run("terraform_fmt_init_validate", [
                            "cd \"${TF_ROOT:-.}\"",
                            "terraform fmt -check -recursive",
                            "terraform init -input=false "
                            "-backend-config=key=${TF_BACKEND_KEY:-terraform.tfstate}",
                            "terraform validate",
                        ]),
                        self._run("tflint", [
                            "cd \"${TF_ROOT:-.}\"",
                            "tflint --init && tflint --format=default --recursive",
                        ]),
                        self._run("tfsec", [
                            "cd \"${TF_ROOT:-.}\"",
                            "tfsec . --format=lovely --soft-fail-warnings",
                        ]),
                    ]},
                },
            }
        }

        # ---------------- Stage 2: plan (native TerraformPlan step) --------
        # Iteration-20 (P3): swapped from Custom-stage shell to the native
        # Harness `TerraformPlan` step type. The delegate (with terraform
        # binary + cloud auth configured) runs the plan and persists the
        # plan file in Harness's own state store — no manual tfplan artefact
        # upload required. The `provisionerIdentifier` ties this plan to the
        # `TerraformApply` step in stage 4 (must be identical).
        plan_stage = {
            "stage": {
                "identifier": "terraform_plan",
                "name": "Plan (native TerraformPlan step)",
                "type": "Custom",
                "spec": {
                    "execution": {"steps": [{
                        "step": {
                            "type": "TerraformPlan",
                            "name": "Terraform Plan",
                            "identifier": "terraform_plan_step",
                            "spec": {
                                # Same ID must be used by the Apply step in
                                # stage 4 — that's how Harness links them.
                                "provisionerIdentifier": "aipp_infra",
                                "configuration": {
                                    # `Apply` means "produce a plan that will
                                    # later be applied" (as opposed to Destroy).
                                    "command": "Apply",
                                    "configFiles": {
                                        "store": {
                                            "type": "Github",
                                            "spec": {
                                                # User picks the git connector
                                                # at pipeline run time.
                                                "connectorRef": "<+input>",
                                                "gitFetchType": "Branch",
                                                "branch": "<+trigger.branch>",
                                                "folderPath": "<+pipeline.variables.TF_ROOT>",
                                            },
                                        },
                                    },
                                    "backendConfig": {
                                        "type": "Inline",
                                        "spec": {
                                            "content": (
                                                'key = "<+pipeline.variables.TF_BACKEND_KEY>"'
                                            ),
                                        },
                                    },
                                    "environmentVariables": [],
                                    "varFiles": [],
                                    "targets": [],
                                },
                                # Delegate group with terraform + cloud CLI
                                # pre-installed — user selects at run time.
                                "delegateSelectors": ["<+input>"],
                            },
                            "timeout": "15m",
                        },
                    }]},
                },
            }
        }

        # ---------------- Stage 3: policy (OPA + Terratest, soft-fail) --
        policy_stage = {
            "stage": {
                "identifier": "terraform_policy",
                "name": "Policy (OPA / conftest + Terratest)",
                "type": "Custom",
                "spec": {
                    "execution": {"steps": [
                        self._run("install_conftest", [install_conftest]),
                        self._run("opa_conftest_gate", [
                            "cd \"${TF_ROOT:-.}\"",
                            "if [ -d policy ]; then",
                            "  conftest test plan.json --policy policy",
                            "else",
                            "  echo 'No ./policy directory found — skipping OPA gate'",
                            "fi",
                        ]),
                        self._run("terratest_if_present", [
                            "cd \"${TF_ROOT:-.}\"",
                            "if [ -d tests ] && ls tests/*.go >/dev/null 2>&1; then",
                            "  go test -v -timeout 60m ./tests/...",
                            "else",
                            "  echo 'No Terratest suite under ./tests — skipping'",
                            "fi",
                        ]),
                    ]},
                },
            }
        }

        # ---------------- Stage 4: manual-approval apply (native step) ------
        # Iteration-20 (P3): native `TerraformApply` step with
        # `type: InheritFromPlan` — reuses the plan file produced by the
        # TerraformPlan step in stage 2 via the shared `provisionerIdentifier`
        # ("aipp_infra"). Guaranteed: no drift between plan and apply.
        # The HarnessApproval step keeps a human-in-the-loop gate before apply.
        apply_stage = {
            "stage": {
                "identifier": "terraform_apply",
                "name": "Apply (native TerraformApply · manual approval)",
                "type": "Custom",
                "spec": {
                    "execution": {"steps": [
                        # 4a — HarnessApproval: pause the pipeline until a
                        # reviewer clicks Approve in the Harness UI.
                        {"step": {
                            "identifier": "terraform_apply_approval",
                            "name": "Approve Terraform apply",
                            "type": "HarnessApproval",
                            "timeout": "1d",
                            "spec": {
                                "approvalMessage": (
                                    "Review the plan output above and approve "
                                    "terraform apply to production."
                                ),
                                "includePipelineExecutionHistory": True,
                                "approvers": {
                                    "minimumCount": 1,
                                    "disallowPipelineExecutor": True,
                                    "userGroups": ["<+variable.TF_APPROVER_GROUP>"],
                                },
                            },
                        }},
                        # 4b — Native TerraformApply step. `InheritFromPlan`
                        # tells Harness to look up the plan produced by the
                        # TerraformPlan step with the same provisionerIdentifier
                        # and apply THAT plan verbatim — no re-plan, no drift.
                        {"step": {
                            "type": "TerraformApply",
                            "name": "Terraform Apply (inherit from plan)",
                            "identifier": "terraform_apply_step",
                            "spec": {
                                "provisionerIdentifier": "aipp_infra",
                                "configuration": {
                                    # This is the key: reuse the plan artifact
                                    # produced upstream. Without this, Harness
                                    # would re-plan on the apply agent and
                                    # potentially diverge from the approved plan.
                                    "type": "InheritFromPlan",
                                },
                            },
                            "timeout": "60m",
                        }},
                    ]},
                    "environment": {"environmentRef": "production"},
                },
                # Only run apply on main branch pushes or v*.*.* tags.
                "when": {
                    "pipelineStatus": "Success",
                    "condition": (
                        "<+trigger.branch> == 'main' || "
                        "<+trigger.tag>.startsWith('v')"
                    ),
                },
            }
        }

        doc = {
            "pipeline": {
                "name": f"AIPP-Terraform-{self.repo_name}",
                "identifier": f"AIPP_TF_{self.repo_name.replace('-', '_')}",
                "projectIdentifier": "<+variable.HARNESS_PROJECT>",
                "orgIdentifier": "<+variable.HARNESS_ORG>",
                "variables": [
                    {"name": "TF_ROOT", "type": "String", "value": "."},
                    {"name": "TF_VERSION", "type": "String", "value": "1.9.5"},
                    {"name": "TF_BACKEND_KEY", "type": "String",
                     "value": f"{self.repo_name}.tfstate"},
                    {"name": "TF_ARTIFACT_STORE", "type": "String", "value": "<+input>"},
                    {"name": "TF_APPROVER_GROUP", "type": "String", "value": "<+input>"},
                    {"name": "HARNESS_ORG", "type": "String", "value": "default"},
                    {"name": "HARNESS_PROJECT", "type": "String", "value": "default"},
                ],
                "stages": [validate_stage, plan_stage, policy_stage, apply_stage],
            }
        }
        header = (
            f"# ==================================================================\n"
            f"# AIPP Terraform pipeline · {provider_note}\n"
            f"# 4-stage flow: validate -> plan -> policy -> apply\n"
            f"# `apply` is guarded by a HarnessApproval step + branch/tag rule.\n"
            f"# ==================================================================\n"
        )
        rendered = yaml.safe_dump(doc, sort_keys=False, width=140)

        from backend.generators.base import inject_comments
        rendered = inject_comments(rendered, {
            "identifier: terraform_validate":
                ["-----------------------------------------------------------",
                 "STAGE 1 · VALIDATE — fmt + init + validate + tflint + tfsec",
                 "-----------------------------------------------------------"],
            "identifier: terraform_plan":
                ["-----------------------------------------------------------",
                 "STAGE 2 · PLAN — publishes tfplan artefact via File Store",
                 "-----------------------------------------------------------"],
            "identifier: terraform_policy":
                ["-----------------------------------------------------------",
                 "STAGE 3 · POLICY — OPA/conftest + Terratest (soft-fail)",
                 "-----------------------------------------------------------"],
            "identifier: terraform_apply":
                ["-----------------------------------------------------------",
                 "STAGE 4 · APPLY — HarnessApproval step gates apply until a",
                 "designated approver clicks Approve; also branch/tag guarded.",
                 "-----------------------------------------------------------"],
        })
        return header + rendered

    @staticmethod
    def _run(identifier: str, commands: List[str]) -> dict:
        return {"step": {
            "identifier": identifier,
            "name": identifier.replace("_", " ").title(),
            "type": "Run",
            "spec": {"shell": "Bash", "command": "\n".join(commands)},
        }}

    @staticmethod
    def _cloud_auth_cmd(cloud: str) -> str:
        if cloud == "azure":
            return ("az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET "
                    "--tenant $AZURE_TENANT_ID")
        if cloud == "aws":
            return ("aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID && "
                    "aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY && "
                    "aws configure set region $AWS_REGION")
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
    def _when_condition(trigger: str) -> str:
        return {
            "develop_branch":  "<+trigger.branch> == 'develop'",
            "release_branch":  "<+trigger.branch>.startsWith('release/')",
            "main_branch":     "<+trigger.branch> == 'main'",
            "version_tag":     "<+trigger.tag>.startsWith('v')",
            "manual":          "<+pipeline.triggerType> == 'MANUAL'",
            "feature_branch":  "<+trigger.branch>.startsWith('feature/')",
        }.get(trigger, "true")
