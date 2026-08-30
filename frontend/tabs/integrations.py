"""Integrations tab — onboard deployment platforms + view deploy history.

Iteration-25 (Auto-Deploy).

Two panels:
  1. **Onboard** — user adds a deployment target (GitHub Actions or Azure
     DevOps). Nickname, repo URL, default branch, PAT.
  2. **My Integrations** — list, test-connection, and delete existing
     targets. Also renders the last 100 deployments as an audit log.

All calls are authenticated with the JWT stored in Gradio state at login.
"""

from __future__ import annotations

import gradio as gr

from frontend.components.api_client import delete, get, post


PLATFORM_CHOICES = [
    ("GitHub Actions (github.com)", "github_actions"),
    ("Azure DevOps (dev.azure.com)", "azure_devops"),
    ("GitLab CI (gitlab.com / self-hosted)", "gitlab_ci"),
]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _fmt_targets(token: str) -> str:
    if not token:
        return "_Sign in first to view your integrations._"
    try:
        payload = get("/api/integrations/targets", token=token)
    except Exception as e:
        return f"⚠ Could not load integrations: `{e}`"
    items = payload.get("targets", []) or []
    if not items:
        return (
            "_No tool credentials yet._\n\n"
            "Use the form above to onboard a GitHub / Azure DevOps / GitLab "
            "PAT for auto-deploy. The token you paste is Fernet-encrypted at rest. "
            "The exact deployment repo URL is picked at push time on the "
            "**Pipeline Generator** page."
        )
    rows = [
        "| # | Nickname | Platform | Saved default repo (optional) | ID |",
        "|--:|----------|----------|-------------------------------|----|",
    ]
    for i, t in enumerate(items, start=1):
        repo_col = (
            f"[{t['repo_url']}]({t['repo_url']}) · `{t['default_branch']}`"
            if t.get("repo_url") else "_(picked per deployment)_"
        )
        rows.append(
            f"| {i} | **{t['name']}** | `{t['platform']}` | "
            f"{repo_col} | `{t['id'][:8]}…` |"
        )
    return "\n".join(rows)


def _fmt_deployments(token: str) -> str:
    if not token:
        return "_Sign in to view deployment history._"
    try:
        payload = get("/api/integrations/deployments", token=token)
    except Exception as e:
        return f"⚠ Could not load history: `{e}`"
    items = payload.get("deployments", []) or []
    if not items:
        return "_No deployments yet._"
    rows = [
        "| When | Platform | Repo | Branch | Mode | Status | Link |",
        "|------|----------|------|--------|------|--------|------|",
    ]
    for d in items:
        ts = (d.get("created_at") or "")[:19].replace("T", " ")
        status = d.get("status", "?")
        badge = {"success": "✅", "failed": "❌", "pending": "…"}.get(status, status)
        link = d.get("ref_url") or ""
        link_md = f"[open]({link})" if link else "—"
        rows.append(
            f"| `{ts}` | `{d['platform']}` | "
            f"`{d['repo_url'].split('/')[-2]}/{d['repo_url'].split('/')[-1]}` | "
            f"`{d['branch']}` | `{d['mode']}` | {badge} {status} | {link_md} |"
        )
    if any(d.get("error") for d in items):
        rows.append("\n**Recent errors**\n")
        for d in items[:20]:
            if d.get("error"):
                rows.append(f"- `{d['id'][:8]}` — {d['error']}")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def _create(name, platform, pat, token):
    if not token:
        return "⚠ Please sign in first.", _fmt_targets(token)
    if not (name and platform and pat):
        return "⚠ Nickname, platform and PAT are all required.", _fmt_targets(token)
    try:
        post(
            "/api/integrations/targets",
            token=token,
            json={
                "name": name.strip(),
                "platform": platform,
                # Repo URL + branch are now picked at push time on the
                # Pipeline Generator page — an Integration is just an
                # authenticated tool credential now (iteration-26.7).
                "repo_url": "",
                "default_branch": "main",
                "token": pat.strip(),
            },
        )
    except Exception as e:
        return f"❌ {e}", _fmt_targets(token)
    return (
        f"✅ Onboarded **{name}**. Token stored Fernet-encrypted. "
        "Head to the Pipeline Generator to pick a deployment repo and auto-push.",
        _fmt_targets(token),
    )


def _test(target_id, token):
    if not token:
        return "⚠ Please sign in first."
    if not target_id:
        return "⚠ Paste the target ID (first column of the table) first."
    try:
        r = post(f"/api/integrations/targets/{target_id.strip()}/test",
                 token=token, json={})
    except Exception as e:
        return f"❌ {e}"
    return (
        f"✅ Connection OK — `{r.get('name') or r.get('platform')}` · "
        f"default branch `{r.get('default_branch','?')}`"
    )


def _delete(target_id, token):
    if not token:
        return "⚠ Please sign in first.", _fmt_targets(token)
    if not target_id:
        return "⚠ Paste the target ID first.", _fmt_targets(token)
    try:
        delete(f"/api/integrations/targets/{target_id.strip()}", token=token)
    except Exception as e:
        return f"❌ {e}", _fmt_targets(token)
    return "✅ Removed.", _fmt_targets(token)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def build_tab(token_state: gr.State) -> None:
    with gr.Column():
        gr.Markdown(
            "## Deployment Integrations · Tool credentials only\n"
            "Onboard a **tool credential** (GitHub Actions / Azure DevOps / "
            "GitLab CI) with a write-scoped PAT. The **deployment repo URL "
            "and branch are picked on the Pipeline Generator page** at push "
            "time — that way one integration can push into many repos "
            "belonging to the same tool tenant.\n\n"
            "🔒 **How your credentials are stored:** the PAT you paste is "
            "encrypted with `Fernet` (`AIPP_FERNET_KEY`) before it hits the "
            "database. It never appears in logs and is only decrypted in "
            "memory for the exact API call the user triggered."
        )
        with gr.Group():
            gr.Markdown("### 1. Onboard a new tool credential")
            with gr.Row():
                name_in = gr.Textbox(label="Nickname",
                                     placeholder="Prod GitHub org PAT",
                                     elem_id="int-name")
                platform_in = gr.Dropdown(PLATFORM_CHOICES, label="Platform",
                                          value="github_actions",
                                          elem_id="int-platform")
            pat_in = gr.Textbox(label="Access token (PAT)",
                                type="password",
                                info=("GitHub → `repo` + `workflow` scopes. "
                                      "Azure DevOps → Code (Read & Write) + PR create. "
                                      "GitLab → `write_repository` (or `api`)."),
                                elem_id="int-pat")
            add_btn = gr.Button("Add integration", variant="primary",
                                elem_id="int-add")
            add_msg = gr.Markdown(elem_id="int-add-msg")

        with gr.Group():
            gr.Markdown("### 2. My integrations")
            targets_md = gr.Markdown(value="_Loading…_", elem_id="int-targets")
            with gr.Row():
                tid_in = gr.Textbox(label="Target ID (paste from table)",
                                    elem_id="int-tid")
                test_btn = gr.Button("Test connection", elem_id="int-test")
                del_btn = gr.Button("Delete target", variant="stop",
                                    elem_id="int-del")
            action_msg = gr.Markdown(elem_id="int-action-msg")

        with gr.Group():
            gr.Markdown("### 3. Deployment history")
            history_md = gr.Markdown(value="_Loading…_", elem_id="int-history")
            refresh_btn = gr.Button("↻ Refresh", elem_id="int-refresh")

        # ---------- wiring ----------
        add_btn.click(
            _create,
            inputs=[name_in, platform_in, pat_in, token_state],
            outputs=[add_msg, targets_md],
        )
        test_btn.click(_test, inputs=[tid_in, token_state], outputs=[action_msg])
        del_btn.click(_delete, inputs=[tid_in, token_state],
                      outputs=[action_msg, targets_md])
        refresh_btn.click(
            lambda tok: (_fmt_targets(tok), _fmt_deployments(tok)),
            inputs=[token_state],
            outputs=[targets_md, history_md],
        )
        # First render — refresh whenever the token appears (post-login).
        token_state.change(
            lambda tok: (_fmt_targets(tok), _fmt_deployments(tok)),
            inputs=[token_state],
            outputs=[targets_md, history_md],
        )
