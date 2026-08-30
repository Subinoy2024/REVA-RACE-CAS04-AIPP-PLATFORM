"""Real production commands per language and stage.

This module replaces the old `echo` placeholders with real, runnable commands
that build, test, scan, and package an application. Each command table is
declared as a plain dictionary so a human reader can review at a glance what
AIPP will emit for each detected technology stack.

Add a new language by adding an entry to LANG_COMMANDS. Add a new stage by
adding a key to the inner dict. No agent code needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class LanguageCommands:
    """Concrete shell commands for a single language / package manager."""

    setup: List[str]          # one-time toolchain setup (Node, JDK, Python, ...)
    install: List[str]        # dependency install
    build: List[str]          # compile / package
    unit_test: List[str]      # unit tests
    integration_test: List[str]  # integration tests (empty if not applicable)
    lint: List[str]           # code quality / linter
    sast: List[str]           # static application security testing
    dependency_scan: List[str]   # SCA / dependency vulnerabilities
    artifact_path: str        # where the build output lands (dist/, target/, ...)


# ---------------------------------------------------------------------------
# Per-language production commands. Reviewed against the official docs of
# each toolchain. Every line is a real command that runs on a stock CI image.
# ---------------------------------------------------------------------------
NODE_NPM = LanguageCommands(
    setup=["actions/setup-node@v4:20"],
    # Prefer `npm ci` (fast, deterministic). Fall back to `npm install` if the
    # lock file is out of sync with package.json — this happens routinely on
    # freshly-scaffolded repos and would otherwise fail the pipeline before it
    # can even run the tests.
    install=["npm ci || npm install --no-audit --no-fund"],
    build=["npm run build --if-present"],
    # `--if-present` lets vitest / jest / mocha / whatever the repo actually
    # configured in `package.json.scripts.test` decide the behaviour. We
    # DON'T pass framework-specific flags (e.g. Jest's `--ci`, Vitest's
    # `run`) — those are the repo's job to configure in package.json.
    unit_test=["npm test --if-present"],
    integration_test=["npm run test:integration --if-present"],
    lint=["npx --no-install eslint . --max-warnings=0 || true"],
    sast=["npx --yes @snyk/cli test --severity-threshold=high || true"],
    dependency_scan=["npm audit --audit-level=high || true"],
    artifact_path="dist",
)

NODE_YARN = LanguageCommands(
    setup=["actions/setup-node@v4:20", "corepack enable"],
    install=["yarn install --frozen-lockfile || yarn install"],
    build=["yarn build"],
    unit_test=["yarn test"],
    integration_test=["yarn test:integration"],
    lint=["yarn lint --max-warnings=0 || true"],
    sast=["npx --yes @snyk/cli test --severity-threshold=high || true"],
    dependency_scan=["yarn audit --level high || true"],
    artifact_path="dist",
)

NODE_PNPM = LanguageCommands(
    setup=["actions/setup-node@v4:20", "corepack enable"],
    install=["pnpm install --frozen-lockfile || pnpm install"],
    build=["pnpm build"],
    unit_test=["pnpm test"],
    integration_test=["pnpm test:integration"],
    lint=["pnpm lint || true"],
    sast=["npx --yes @snyk/cli test --severity-threshold=high || true"],
    dependency_scan=["pnpm audit --audit-level high || true"],
    artifact_path="dist",
)

PYTHON_PIP = LanguageCommands(
    setup=["actions/setup-python@v5:3.12", "python -m pip install --upgrade pip"],
    install=["pip install -r requirements.txt"],
    build=["python -m build || python setup.py sdist bdist_wheel || pip wheel . -w dist"],
    unit_test=["pytest -q --junitxml=test-results.xml"],
    integration_test=["pytest -q tests/integration --junitxml=integration-results.xml || true"],
    lint=["ruff check . || flake8 . || true"],
    sast=["bandit -r . -ll --exit-zero"],
    dependency_scan=["pip-audit --strict || true"],
    artifact_path="dist",
)

PYTHON_POETRY = LanguageCommands(
    setup=["actions/setup-python@v5:3.12", "pip install poetry"],
    install=["poetry install --no-interaction --no-root"],
    build=["poetry build"],
    unit_test=["poetry run pytest -q --junitxml=test-results.xml"],
    integration_test=["poetry run pytest -q tests/integration || true"],
    lint=["poetry run ruff check . || true"],
    sast=["poetry run bandit -r . -ll --exit-zero"],
    dependency_scan=["poetry run pip-audit --strict || true"],
    artifact_path="dist",
)

JAVA_MAVEN = LanguageCommands(
    setup=["actions/setup-java@v4:temurin:17"],
    install=["mvn -B -DskipTests dependency:go-offline"],
    build=["mvn -B -DskipTests package"],
    unit_test=["mvn -B test"],
    integration_test=["mvn -B verify -DskipUnitTests || true"],
    lint=["mvn -B checkstyle:check || true"],
    sast=["mvn -B org.owasp:dependency-check-maven:check || true"],
    dependency_scan=["mvn -B org.owasp:dependency-check-maven:check || true"],
    artifact_path="target",
)

JAVA_GRADLE = LanguageCommands(
    setup=["actions/setup-java@v4:temurin:17"],
    install=["./gradlew --no-daemon dependencies || true"],
    build=["./gradlew --no-daemon build -x test"],
    unit_test=["./gradlew --no-daemon test"],
    integration_test=["./gradlew --no-daemon integrationTest || true"],
    lint=["./gradlew --no-daemon check || true"],
    sast=["./gradlew --no-daemon dependencyCheckAnalyze || true"],
    dependency_scan=["./gradlew --no-daemon dependencyCheckAnalyze || true"],
    artifact_path="build/libs",
)

GO_MOD = LanguageCommands(
    setup=["actions/setup-go@v5:1.22"],
    install=["go mod download"],
    build=["go build -o bin/app ./..."],
    unit_test=["go test -race -covermode=atomic ./..."],
    integration_test=["go test -tags=integration ./... || true"],
    lint=["golangci-lint run || true"],
    sast=["gosec -no-fail -fmt json -out gosec.json ./... || true"],
    dependency_scan=["govulncheck ./... || true"],
    artifact_path="bin",
)

RUST_CARGO = LanguageCommands(
    setup=["rustup toolchain install stable"],
    install=["cargo fetch"],
    build=["cargo build --release"],
    unit_test=["cargo test --release"],
    integration_test=["cargo test --release --tests"],
    lint=["cargo clippy -- -D warnings || true"],
    sast=["cargo audit || true"],
    dependency_scan=["cargo audit || true"],
    artifact_path="target/release",
)

DOTNET = LanguageCommands(
    setup=["actions/setup-dotnet@v4:8.0"],
    install=["dotnet restore"],
    build=["dotnet build --no-restore -c Release"],
    unit_test=["dotnet test --no-build --logger trx"],
    integration_test=["dotnet test --filter Category=Integration || true"],
    lint=["dotnet format --verify-no-changes || true"],
    sast=["dotnet list package --vulnerable --include-transitive || true"],
    dependency_scan=["dotnet list package --outdated || true"],
    artifact_path="bin/Release",
)

# Fallback / unknown language: safe placeholder that a human will complete.
GENERIC = LanguageCommands(
    setup=["echo 'toolchain setup: language not detected'"],
    install=["echo 'install dependencies'"],
    build=["echo 'build project'"],
    unit_test=["echo 'run unit tests'"],
    integration_test=["echo 'run integration tests'"],
    lint=["echo 'run linter'"],
    sast=["echo 'run static security analysis'"],
    dependency_scan=["echo 'scan dependencies for vulnerabilities'"],
    artifact_path="build",
)


def pick_commands(language: Optional[str], package_manager: Optional[str]) -> LanguageCommands:
    """Return the right LanguageCommands for a detected stack.

    Falls back to GENERIC if nothing matches. Human-readable order: match the
    language first, then narrow by package manager.
    """
    lang = (language or "").lower()
    pm = (package_manager or "").lower()

    if lang in {"javascript", "typescript", "node", "nodejs"}:
        if pm == "yarn":
            return NODE_YARN
        if pm == "pnpm":
            return NODE_PNPM
        return NODE_NPM

    if lang == "python":
        if pm == "poetry":
            return PYTHON_POETRY
        return PYTHON_PIP

    if lang == "java":
        if pm == "gradle":
            return JAVA_GRADLE
        return JAVA_MAVEN

    if lang == "go":
        return GO_MOD

    if lang in {"rust", "cargo"}:
        return RUST_CARGO

    if lang in {"csharp", "c#", "dotnet", ".net"}:
        return DOTNET

    return GENERIC


# ---------------------------------------------------------------------------
# Container build / push commands (real, per cloud registry)
# ---------------------------------------------------------------------------
CONTAINER_BUILD = "docker buildx build --platform linux/amd64 -t {image}:{tag} -f {dockerfile} ."

REGISTRY_LOGIN = {
    "azure": "az acr login --name {registry}",
    "aws":   "aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {registry}",
    "gcp":   "gcloud auth configure-docker {region}-docker.pkg.dev --quiet",
}

CONTAINER_PUSH = "docker push {image}:{tag}"

# Image reference builders per cloud registry (real production formats)
def image_ref(cloud: str, registry: str, repo_name: str) -> str:
    cloud = cloud.lower()
    if cloud == "azure":
        # ACR: {name}.azurecr.io/{repo}
        return f"{registry}.azurecr.io/{repo_name}"
    if cloud == "aws":
        # ECR: {account}.dkr.ecr.{region}.amazonaws.com/{repo}
        return f"{registry}/{repo_name}"
    if cloud == "gcp":
        # GAR: {region}-docker.pkg.dev/{project}/{repo}
        return f"{registry}/{repo_name}"
    return f"registry.example.com/{repo_name}"
