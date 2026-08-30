"""Contract tests for `.env.example` (single-source-of-truth model).

Iteration-25.x note:
    AIPP used to ship TWO `.env.example` files (root + backend/) and they
    had to stay byte-identical. That model was error-prone — users edited
    one and forgot the other, breaking Postgres auth. We now ship exactly
    one file at the repo root. `backend/.env.example` still exists but is
    a short redirect stub pointing users at the real one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT_ENV_EXAMPLE = Path("/app/.env.example")
BACKEND_ENV_EXAMPLE = Path("/app/backend/.env.example")

# Every one of these must exist as a key in `.env.example` — they are
# the minimum a user needs to boot AIPP.
REQUIRED_KEYS = [
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "JWT_SECRET",
    "AIPP_DEFAULT_ADMIN_EMAIL",
    "AIPP_DEFAULT_ADMIN_PASSWORD",
    "AIPP_FERNET_KEY",
]

# Optional adapter/integration keys — must at least appear (blank value is fine)
OPTIONAL_KEYS = [
    "AIPP_LLM_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
    "N8N_BASE_URL", "N8N_API_KEY",
    "OIDC_PROVIDER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_DISCOVERY_URL",
    "RESEND_API_KEY", "EMAIL_FROM",
]


class TestSingleSourceOfTruth:
    """Only `.env` at the repo root is authoritative."""

    def test_root_env_example_exists(self):
        assert ROOT_ENV_EXAMPLE.exists(), "root .env.example missing"

    def test_backend_env_example_is_a_redirect_stub(self):
        """backend/.env.example should exist but be a small redirect note,
        NOT a full duplicate of the root file (which caused drift bugs)."""
        assert BACKEND_ENV_EXAMPLE.exists(), "backend/.env.example missing"
        assert BACKEND_ENV_EXAMPLE.stat().st_size < 500, (
            "backend/.env.example is too large — it should be a small "
            "redirect stub, not a duplicate of the root .env.example."
        )
        text = BACKEND_ENV_EXAMPLE.read_text().lower()
        assert "removed" in text or "single" in text or "root" in text, (
            "backend/.env.example must explain that the real file is at repo root"
        )

    def test_derived_url_keys_absent(self):
        """`.env.example` must NOT ship `DATABASE_URL` / `POSTGRES_URL` /
        `POSTGRES_SYNC_URL` — those are derived by docker-compose from
        POSTGRES_USER + POSTGRES_PASSWORD + POSTGRES_DB. Shipping them
        would re-introduce the drift bug we just fixed."""
        text = ROOT_ENV_EXAMPLE.read_text()
        for banned in ("DATABASE_URL=", "POSTGRES_URL=", "POSTGRES_SYNC_URL="):
            assert banned not in text, (
                f"'{banned}' must not appear in .env.example — Docker Compose "
                f"derives it from POSTGRES_* to keep backend + Postgres in sync"
            )


class TestEnvExampleContent:
    def setup_method(self):
        self.values = dotenv_values(ROOT_ENV_EXAMPLE)
        self.text = ROOT_ENV_EXAMPLE.read_text()

    def test_all_required_keys_present(self):
        missing = [k for k in REQUIRED_KEYS if k not in self.values]
        assert not missing, f"Missing required keys: {missing}"

    def test_optional_keys_present(self):
        missing = [k for k in OPTIONAL_KEYS if k not in self.values]
        assert not missing, f"Missing optional keys: {missing}"

    def test_dotenv_parses_cleanly_no_none_values(self):
        bad = [k for k, v in self.values.items() if v is None]
        assert not bad, f"Keys without '=' delimiter: {bad}"

    def test_postgres_defaults_sensible(self):
        """User + DB should be non-empty; password is allowed to be a
        placeholder default the operator will override in production."""
        assert self.values.get("POSTGRES_USER"),  "POSTGRES_USER must have a default"
        assert self.values.get("POSTGRES_DB"),    "POSTGRES_DB must have a default"
        assert self.values.get("POSTGRES_PASSWORD"), "POSTGRES_PASSWORD must have a default"


class TestUserCopyFlow:
    """Simulate `cp .env.example .env` from the repo root."""
    TMP_COPY = Path("/tmp/user_env_test_root")

    def teardown_method(self):
        if self.TMP_COPY.exists():
            self.TMP_COPY.unlink()

    def test_cp_from_repo_root_gives_a_bootable_env(self):
        result = subprocess.run(
            ["cp", ".env.example", str(self.TMP_COPY)],
            cwd="/app", capture_output=True, text=True,
        )
        assert result.returncode == 0, f"cp failed: {result.stderr}"
        values = dotenv_values(self.TMP_COPY)
        for k in REQUIRED_KEYS:
            assert k in values, f"required key missing after cp: {k}"
