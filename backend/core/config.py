"""AIPP core settings loaded from environment (.env).

Keeps all configuration in one place so no other module reads env vars directly.
The user can supply their own LLM API key (per-vendor) or a single universal
key via `AIPP_LLM_KEY` — no code changes needed.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


class Settings(BaseModel):
    # --- Database -----------------------------------------------------------
    postgres_url: str = Field(
        default_factory=lambda: os.environ.get(
            "POSTGRES_URL",
            "postgresql+asyncpg://aipp:aipp_local@127.0.0.1:5432/aipp",
        )
    )
    postgres_sync_url: str = Field(
        default_factory=lambda: os.environ.get(
            "POSTGRES_SYNC_URL",
            "postgresql+psycopg2://aipp:aipp_local@127.0.0.1:5432/aipp",
        )
    )

    # --- LLM ---------------------------------------------------------------
    # `AIPP_LLM_KEY` is the universal / customer-provided key. For backwards
    # compatibility we also honour the legacy `EMERGENT_LLM_KEY` if present,
    # but user-facing docs & UI only advertise `AIPP_LLM_KEY`.
    aipp_llm_key: Optional[str] = Field(default_factory=lambda: (
        os.environ.get("AIPP_LLM_KEY")
        or os.environ.get("EMERGENT_LLM_KEY")
        or None
    ))
    anthropic_api_key: Optional[str] = Field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY") or None)
    openai_api_key: Optional[str] = Field(default_factory=lambda: os.environ.get("OPENAI_API_KEY") or None)
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.environ.get("GEMINI_API_KEY") or None)
    llm_provider: Literal["anthropic", "openai", "gemini"] = Field(
        default_factory=lambda: os.environ.get("LLM_PROVIDER", "anthropic")  # type: ignore
    )
    llm_model: str = Field(default_factory=lambda: os.environ.get("LLM_MODEL", "claude-sonnet-4-6"))

    # --- n8n ---------------------------------------------------------------
    n8n_base_url: Optional[str] = Field(default_factory=lambda: os.environ.get("N8N_BASE_URL") or None)
    n8n_api_key: Optional[str] = Field(default_factory=lambda: os.environ.get("N8N_API_KEY") or None)

    # --- CI/CD MCP adapter credentials -----------------------------------
    azure_devops_org_url: Optional[str] = Field(default_factory=lambda: os.environ.get("AZURE_DEVOPS_ORG_URL") or None)
    azure_devops_pat: Optional[str] = Field(default_factory=lambda: os.environ.get("AZURE_DEVOPS_PAT") or None)

    gitlab_url: str = Field(default_factory=lambda: os.environ.get("GITLAB_URL", "https://gitlab.com"))
    gitlab_token: Optional[str] = Field(default_factory=lambda: os.environ.get("GITLAB_TOKEN") or None)

    github_actions_token: Optional[str] = Field(default_factory=lambda: os.environ.get("GITHUB_ACTIONS_TOKEN") or None)

    harness_base_url: str = Field(default_factory=lambda: os.environ.get("HARNESS_BASE_URL", "https://app.harness.io"))
    harness_account_id: Optional[str] = Field(default_factory=lambda: os.environ.get("HARNESS_ACCOUNT_ID") or None)
    harness_api_key: Optional[str] = Field(default_factory=lambda: os.environ.get("HARNESS_API_KEY") or None)

    kubeconfig_path: Optional[str] = Field(default_factory=lambda: os.environ.get("KUBECONFIG") or None)

    # --- Cloud MCP adapter credentials -----------------------------------
    azure_subscription_id: Optional[str] = Field(default_factory=lambda: os.environ.get("AZURE_SUBSCRIPTION_ID") or None)
    azure_tenant_id: Optional[str] = Field(default_factory=lambda: os.environ.get("AZURE_TENANT_ID") or None)
    azure_client_id: Optional[str] = Field(default_factory=lambda: os.environ.get("AZURE_CLIENT_ID") or None)
    azure_client_secret: Optional[str] = Field(default_factory=lambda: os.environ.get("AZURE_CLIENT_SECRET") or None)

    aws_access_key_id: Optional[str] = Field(default_factory=lambda: os.environ.get("AWS_ACCESS_KEY_ID") or None)
    aws_secret_access_key: Optional[str] = Field(default_factory=lambda: os.environ.get("AWS_SECRET_ACCESS_KEY") or None)
    aws_region: str = Field(default_factory=lambda: os.environ.get("AWS_REGION", "us-east-1"))

    gcp_project_id: Optional[str] = Field(default_factory=lambda: os.environ.get("GCP_PROJECT_ID") or None)
    gcp_service_account_json: Optional[str] = Field(default_factory=lambda: os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or None)

    # --- Runtime -----------------------------------------------------------
    max_log_upload_bytes: int = Field(default_factory=lambda: int(os.environ.get("MAX_LOG_UPLOAD_BYTES", "5000000")))
    log_level: str = Field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    cors_origins: str = Field(default_factory=lambda: os.environ.get("CORS_ORIGINS", "*"))
    internal_backend_url: str = Field(
        default_factory=lambda: os.environ.get("AIPP_INTERNAL_BACKEND_URL", "http://127.0.0.1:8001")
    )

    # --- Auth --------------------------------------------------------------
    # JWT_SECRET must be a long random string. In dev we fall back to a
    # stable placeholder so tests run without extra env setup, but a
    # production deploy MUST set a real secret.
    jwt_secret: str = Field(default_factory=lambda: os.environ.get(
        "JWT_SECRET", "aipp-dev-secret-please-override-in-prod-64-chars-of-entropy"
    ))
    jwt_access_ttl_minutes: int = Field(default_factory=lambda: int(os.environ.get("JWT_ACCESS_TTL_MINUTES", "1440")))
    admin_email: str = Field(default_factory=lambda: os.environ.get("AIPP_DEFAULT_ADMIN_EMAIL", "admin@aipp.local"))
    admin_password: str = Field(default_factory=lambda: os.environ.get("AIPP_DEFAULT_ADMIN_PASSWORD", "aipp-change-me"))

    # --- OIDC (Google Workspace / Azure AD / any OIDC-compliant IdP) -------
    # Set OIDC_PROVIDER=google|azure to enable the "Sign in with SSO" button.
    # OIDC_DISCOVERY_URL lets you point at any OIDC-compliant provider.
    oidc_provider: str = Field(default_factory=lambda: (os.environ.get("OIDC_PROVIDER") or "off").strip().lower())
    oidc_client_id: str = Field(default_factory=lambda: os.environ.get("OIDC_CLIENT_ID", ""))
    oidc_client_secret: str = Field(default_factory=lambda: os.environ.get("OIDC_CLIENT_SECRET", ""))
    oidc_discovery_url: str = Field(default_factory=lambda: os.environ.get("OIDC_DISCOVERY_URL", ""))
    oidc_tenant_id: str = Field(default_factory=lambda: os.environ.get("OIDC_TENANT_ID", "common"))
    aipp_public_url: str = Field(default_factory=lambda: os.environ.get("AIPP_PUBLIC_URL", "http://localhost:3000"))
    aipp_backend_public_url: str = Field(default_factory=lambda: os.environ.get("AIPP_BACKEND_PUBLIC_URL", "http://localhost:8001"))

    # --- Email (Resend) — used by the password-reset flow -----------------
    resend_api_key: str = Field(default_factory=lambda: os.environ.get("RESEND_API_KEY", ""))
    email_from: str = Field(default_factory=lambda: os.environ.get("EMAIL_FROM", "AIPP <noreply@aipp.local>"))

    # --- n8n Proxy (Option 2: AIPP as secret vault) -----------------------
    # Single API key that n8n workflows send in the Authorization header when
    # they call `POST /api/proxy/*`. AIPP validates it, then uses its OWN
    # infra credentials below to make the real API call. Rotating the proxy
    # key rotates access from n8n; rotating the infra creds happens in one
    # place (this file).
    proxy_api_key: str = Field(default_factory=lambda: os.environ.get("PROXY_API_KEY", ""))

    # Infra credentials that AIPP uses on n8n's behalf. Every proxy endpoint
    # reads these from `settings` — never from the request payload.
    k8s_api_url: str = Field(default_factory=lambda: os.environ.get("K8S_API_URL", ""))
    k8s_token: str = Field(default_factory=lambda: os.environ.get("K8S_TOKEN", ""))
    k8s_ca_verify: bool = Field(default_factory=lambda: os.environ.get("K8S_CA_VERIFY", "false").lower() == "true")
    proxmox_url: str = Field(default_factory=lambda: os.environ.get("PROXMOX_URL", ""))
    proxmox_token: str = Field(default_factory=lambda: os.environ.get("PROXMOX_TOKEN", ""))
    proxmox_node: str = Field(default_factory=lambda: os.environ.get("PROXMOX_NODE", ""))
    proxmox_verify_ssl: bool = Field(default_factory=lambda: os.environ.get("PROXMOX_VERIFY_SSL", "false").lower() == "true")
    grafana_url: str = Field(default_factory=lambda: os.environ.get("GRAFANA_URL", ""))
    grafana_api_key: str = Field(default_factory=lambda: os.environ.get("GRAFANA_API_KEY", ""))
    github_pat: str = Field(default_factory=lambda: os.environ.get("GITHUB_PAT", ""))
    github_org: str = Field(default_factory=lambda: os.environ.get("GH_ORG", ""))
    github_repo: str = Field(default_factory=lambda: os.environ.get("GH_REPO", ""))
    iac_repo_owner: str = Field(default_factory=lambda: os.environ.get("IAC_REPO_OWNER", ""))
    iac_repo_name: str = Field(default_factory=lambda: os.environ.get("IAC_REPO_NAME", ""))
    gh_repo_allowlist: str = Field(default_factory=lambda: os.environ.get("GH_REPO_ALLOWLIST", ""))
    ado_org_proxy: str = Field(default_factory=lambda: os.environ.get("ADO_ORG", ""))
    ado_project: str = Field(default_factory=lambda: os.environ.get("ADO_PROJECT", ""))
    ado_pat: str = Field(default_factory=lambda: os.environ.get("ADO_PAT", ""))

    # --- Slack interactivity (HITL Block Kit buttons) --------------------
    # Slack signs every interactive-message payload with an HMAC-SHA256 of
    # the raw request body using this shared secret (found under "Basic
    # Information → Signing Secret" in the Slack app manifest). We verify
    # the signature on every /api/slack/interactions call so a bad actor
    # can't forge approve/reject clicks against production HITL flows.
    slack_signing_secret: str = Field(
        default_factory=lambda: os.environ.get("SLACK_SIGNING_SECRET", ""),
    )

    # -------- Helpers --------
    def active_llm_key(self) -> str:
        """Return the API key that will be sent to the LLM SDK.

        Preference order: user-supplied provider-specific key → `AIPP_LLM_KEY`.
        """
        provider_key = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
        }.get(self.llm_provider)
        if provider_key:
            return provider_key
        if self.aipp_llm_key:
            return self.aipp_llm_key
        raise RuntimeError(
            "No LLM API key configured. Set `AIPP_LLM_KEY` (universal) or a "
            "vendor-specific key (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / "
            "`GEMINI_API_KEY`) in .env"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
