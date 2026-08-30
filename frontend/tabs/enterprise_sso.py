"""Enterprise SSO admin tab — configure Entra ID / Google Workspace / OIDC.

Iteration-26.6.

Post-login page for admins to onboard identity providers without editing
`.env`. Providers added here appear on the login page as `Sign in with X`
buttons alongside any env-configured OIDC.
"""

from __future__ import annotations

import gradio as gr

from frontend.components.api_client import delete as api_delete, get, post


PROVIDER_KINDS = [
    ("Microsoft Entra ID (Azure AD)", "entra"),
    ("Google Workspace",              "google"),
    ("Generic OIDC (custom)",         "oidc"),
]


def _fetch_providers(token: str) -> str:
    if not token:
        return "_Sign in to manage identity providers._"
    try:
        rows = get("/api/auth/identity-providers", token=token) or []
    except Exception as e:
        return f"❌ Could not load providers: `{e}`"
    if not rows:
        return "_No identity providers configured. Add one below._"
    lines = ["| Kind | Display name | Client ID | Enabled | ID |",
             "|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| `{r.get('kind')}` | {r.get('display_name')} | "
            f"`{(r.get('client_id') or '')[:20]}…` | "
            f"{'✅' if r.get('enabled') else '⏸'} | "
            f"`{(r.get('id') or '')[:8]}…` |"
        )
    return "\n".join(lines)


def _add_provider(kind, display_name, client_id, client_secret, discovery_url,
                  tenant_id, token):
    if not token:
        return "⚠ Sign in first."
    if not (display_name and client_id and client_secret):
        return "⚠ Display name, Client ID and Client secret are required."
    body = {
        "kind": kind,
        "display_name": display_name.strip(),
        "client_id": client_id.strip(),
        "client_secret": client_secret,
        "discovery_url": (discovery_url or "").strip() or None,
        "tenant_id": (tenant_id or "").strip() or None,
        "enabled": True,
    }
    try:
        resp = post("/api/auth/identity-providers", json=body, token=token)
    except Exception as e:
        return f"❌ Save failed: `{e}`"
    return f"✅ Added **{resp.get('display_name')}** ({resp.get('kind')})."


def _remove_provider(provider_id, token):
    if not token:
        return "⚠ Sign in first."
    if not provider_id or "…" in provider_id:
        return "⚠ Paste the full provider ID (first 8 chars aren't enough)."
    try:
        api_delete(f"/api/auth/identity-providers/{provider_id.strip()}", token=token)
    except Exception as e:
        return f"❌ Delete failed: `{e}`"
    return f"🗑 Removed provider `{provider_id[:8]}…`."


def build_tab(token_state: gr.State) -> None:
    with gr.Column():
        gr.Markdown(
            "## Enterprise Sign-In\n"
            "Onboard identity providers so your organisation signs into AIPP "
            "with **Microsoft Entra ID**, **Google Workspace**, or any generic "
            "**OIDC** stack. Configuration is stored in Postgres, secrets are "
            "Fernet-encrypted at rest, and providers appear on the login page "
            "as `Sign in with X` buttons on the next reload.\n\n"
            "**No `.env` edit and no container restart required.**"
        )

        with gr.Group():
            gr.Markdown("### Configured providers")
            refresh_btn = gr.Button("↻ Refresh", elem_id="idp-refresh",
                                     variant="secondary")
            providers_md = gr.Markdown(
                "_Click **Refresh** to load._",
                elem_id="idp-list",
            )

        with gr.Group():
            gr.Markdown(
                "### Add a provider\n"
                "**Entra ID:** paste your Application (client) ID + secret. "
                "Set Tenant ID to `common` for multi-tenant apps.  \n"
                "**Google:** create OAuth 2.0 credentials in the Google Cloud "
                "Console with the `openid email profile` scopes.  \n"
                "**Generic OIDC:** provide a discovery URL "
                "(`.well-known/openid-configuration`)."
            )
            with gr.Row():
                kind_in = gr.Dropdown(
                    choices=[(lbl, v) for lbl, v in PROVIDER_KINDS],
                    value="entra",
                    label="Provider kind",
                    elem_id="idp-kind",
                )
                display_in = gr.Textbox(
                    label="Display name (shown on login button)",
                    placeholder="Acme Corp (Entra ID)",
                    elem_id="idp-display",
                )
            with gr.Row():
                client_id_in = gr.Textbox(
                    label="Client ID (Application ID)",
                    elem_id="idp-client-id",
                )
                tenant_in = gr.Textbox(
                    label="Tenant ID (Entra only, leave blank for others)",
                    placeholder="common",
                    elem_id="idp-tenant",
                )
            secret_in = gr.Textbox(
                label="Client secret",
                type="password",
                elem_id="idp-secret",
            )
            discovery_in = gr.Textbox(
                label="Discovery URL (auto-filled for Entra/Google)",
                placeholder="https://.../.well-known/openid-configuration",
                elem_id="idp-discovery",
            )
            add_btn = gr.Button("Save provider", variant="primary",
                                 elem_id="idp-add")
            add_msg = gr.Markdown(elem_id="idp-add-msg")

        with gr.Group():
            gr.Markdown("### Remove a provider")
            del_id_in = gr.Textbox(
                label="Full provider ID (paste from Refresh above)",
                elem_id="idp-del-id",
            )
            del_btn = gr.Button("Delete provider",
                                 variant="stop", elem_id="idp-del")
            del_msg = gr.Markdown(elem_id="idp-del-msg")

        # ---------- wiring ----------
        refresh_btn.click(_fetch_providers, inputs=[token_state],
                          outputs=[providers_md])
        add_btn.click(
            _add_provider,
            inputs=[kind_in, display_in, client_id_in, secret_in,
                    discovery_in, tenant_in, token_state],
            outputs=[add_msg],
        ).then(_fetch_providers, inputs=[token_state], outputs=[providers_md])
        del_btn.click(
            _remove_provider,
            inputs=[del_id_in, token_state],
            outputs=[del_msg],
        ).then(_fetch_providers, inputs=[token_state], outputs=[providers_md])
