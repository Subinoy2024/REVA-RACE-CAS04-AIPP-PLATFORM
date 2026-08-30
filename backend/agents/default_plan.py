"""The AIPP default 6-gate pipeline plan.

When the user does not provide a custom deployment requirement, the Pipeline
Planning agent falls back to this standard structure. It is directly informed
by:

  - DORA / Accelerate research (Forsgren, Humble & Kim, 2018) on the four
    high-performing DevOps metrics.
  - Myrbakken & Colomo-Palacios (2017), DevSecOps multivocal review:
    automation, continuous monitoring, immutable audit trails, security
    gates as first-class citizens.
  - Rausch et al. (2017), MSR: recurring CI/CD failure classes; the default
    catches most of these by construction.

Six mandatory gates + four deployment stages. Each gate is a hard block that
must pass before the pipeline continues. The user can override anything via
the custom requirement free-text field.
"""

from __future__ import annotations

DEFAULT_STAGES = [
    # ---- Gate 1: Build ----
    {
        "name": "build",
        "purpose": "install dependencies and produce the runnable/packaged artifact",
        "tools_hint": "language-native package manager",
        "explanation": "The Build gate compiles the source and packages the "
                       "artifact. It fails fast on missing dependencies.",
    },
    # ---- Gate 2: Test ----
    {
        "name": "unit_test",
        "purpose": "run unit tests with coverage",
        "tools_hint": "language-native test framework",
        "explanation": "Unit tests are cheap and fast; failing here blocks all "
                       "subsequent gates and saves compute.",
    },
    # ---- Gate 3: Security ----
    {
        "name": "sast",
        "purpose": "static application security testing",
        "tools_hint": "SAST scanner (Snyk / Bandit / Semgrep / gosec)",
        "explanation": "Shift-left security. SAST catches known CWE classes "
                       "and secret leakage before any artifact is built.",
    },
    {
        "name": "dependency_scan",
        "purpose": "scan third-party dependencies for known CVEs",
        "tools_hint": "SCA (Snyk / OWASP Dependency-Check / pip-audit)",
        "explanation": "SCA catches vulnerable transitive dependencies "
                       "(Myrbakken & Colomo-Palacios [5]).",
    },
    # ---- Gate 4: Quality ----
    {
        "name": "code_quality",
        "purpose": "linter + formatter check",
        "tools_hint": "language-native linter (ruff / eslint / checkstyle / golangci-lint)",
        "explanation": "Enforces style and catches obvious defects.",
    },
    # ---- Gate 5: Package ----
    {
        "name": "container_build",
        "purpose": "build a container image using the repo Dockerfile",
        "tools_hint": "docker buildx",
        "explanation": "Standardised packaging; produces the immutable artifact "
                       "that flows through all deploy stages.",
    },
    {
        "name": "container_scan",
        "purpose": "scan the built image for OS/lib vulnerabilities",
        "tools_hint": "trivy",
        "explanation": "Second security gate on the packaged artifact.",
    },
    {
        "name": "artifact_publish",
        "purpose": "push the container image to the target cloud registry",
        "tools_hint": "docker push to ACR / ECR / GAR",
        "explanation": "The registry is the source of truth for the deploy "
                       "stages downstream.",
    },
    # ---- Gate 6: Deploy ladder ----
    {
        "name": "deploy_dev",
        "purpose": "deploy to the Development environment automatically",
        "tools_hint": "cloud-native deploy command",
        "explanation": "Triggered on pushes to the develop branch. No approval.",
    },
    {
        "name": "deploy_qa",
        "purpose": "deploy to the QA environment automatically",
        "tools_hint": "cloud-native deploy command",
        "explanation": "Triggered on pushes to release/* branches. No approval.",
    },
    {
        "name": "deploy_staging",
        "purpose": "deploy to the Staging environment automatically",
        "tools_hint": "cloud-native deploy command",
        "explanation": "Triggered on pushes to main. Runs smoke tests after deploy.",
    },
    {
        "name": "deploy_prod",
        "purpose": "deploy to Production with a manual approval gate",
        "tools_hint": "cloud-native deploy command + platform-native approval",
        "explanation": "Triggered on git tag v*.*.*; requires human sign-off.",
    },
]


def default_plan_summary() -> str:
    """One-paragraph summary the Planning agent can include when no custom
    requirement is provided. Written in the author's voice, no jargon."""
    return (
        "No custom requirement was provided, so AIPP applied its standard "
        "6-gate pipeline: build, unit tests, static security analysis, "
        "dependency scan, code quality, then container build + scan + push. "
        "After the gates, the pipeline deploys to Development, QA, Staging "
        "and Production, with Production requiring a manual approval. This "
        "default follows DORA-aligned DevSecOps practice (Myrbakken & "
        "Colomo-Palacios, 2017) and is what most teams need."
    )
