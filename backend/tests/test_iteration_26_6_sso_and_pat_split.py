"""Iteration-26.6 · Enterprise SSO + PAT-split UX — unit tests.

Covers:
  * `IdentityProvider` ORM model
  * `/api/auth/identity-providers` router registration
  * `_autoderive_discovery_url()` derives sane defaults for Entra & Google
  * Auto-Deploy panel default is `auto` (was `manual` → too easy to miss)
  * "Commit YAML to repo" section is now behind an Accordion labelled as
    the LEGACY path (renamed in iteration-26.6)
"""

from __future__ import annotations

import pytest


def test_identity_provider_orm_columns():
    from backend.database.models import IdentityProvider
    cols = {c.name for c in IdentityProvider.__table__.columns}
    expected = {
        "id", "kind", "display_name", "client_id", "client_secret_enc",
        "discovery_url", "tenant_id", "enabled", "created_at",
    }
    assert expected.issubset(cols)


def test_identity_providers_router_registered():
    from backend.server import app
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/auth/identity-providers" in paths
    assert "/api/auth/identity-providers/public" in paths


def test_autoderive_discovery_url_entra_tenant_id():
    from backend.api.identity_providers import _autoderive_discovery_url
    got = _autoderive_discovery_url("entra", "acme-tenant-guid")
    assert "acme-tenant-guid" in got
    assert got.endswith("/v2.0/.well-known/openid-configuration")


def test_autoderive_discovery_url_entra_defaults_to_common():
    from backend.api.identity_providers import _autoderive_discovery_url
    got = _autoderive_discovery_url("entra", None)
    assert "/common/" in got


def test_autoderive_discovery_url_google_fixed():
    from backend.api.identity_providers import _autoderive_discovery_url
    got = _autoderive_discovery_url("google", None)
    assert got == "https://accounts.google.com/.well-known/openid-configuration"


def test_autoderive_discovery_url_oidc_returns_none():
    """Generic OIDC — user must supply their own discovery URL."""
    from backend.api.identity_providers import _autoderive_discovery_url
    assert _autoderive_discovery_url("oidc", None) is None


def test_valid_kinds_are_strict():
    from backend.api.identity_providers import VALID_KINDS
    assert VALID_KINDS == {"entra", "google", "oidc"}


# ---------- PAT-split UX ---------------------------------------------------

def test_pat_hint_mentions_read_only_and_integrations():
    """The GitHub PAT input hint must steer users to the Integrations tab."""
    from pathlib import Path
    src = Path("/app/frontend/tabs/pipeline_generator.py").read_text()
    assert "Read-only PAT is enough" in src
    assert "Integrations" in src


def test_auto_deploy_default_is_auto_not_manual():
    """After iter-26.6 the default is 'auto-push via saved integration'."""
    from pathlib import Path
    src = Path("/app/frontend/tabs/pipeline_generator.py").read_text()
    # Find the block that declares the deploy_choice Radio + its value.
    idx = src.find("deploy_choice = gr.Radio")
    assert idx >= 0
    block = src[idx: idx + 400]
    assert 'value="auto"' in block, block


def test_legacy_commit_panel_now_wrapped_in_accordion():
    """Old 'Commit YAML to repo' section is now the legacy/collapsed path."""
    from pathlib import Path
    src = Path("/app/frontend/tabs/pipeline_generator.py").read_text()
    assert "pg-deploy-legacy-acc" in src
    assert "Advanced — commit into the SAME repo" in src
