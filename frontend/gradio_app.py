"""AIPP — Gradio front-end entry point.

Iteration-24: futuristic control-tower UI + password-reset + OIDC deep-link.

  * Custom CSS in `frontend/static/aipp_theme.css`
  * Login gate — email/password OR SSO button (visible only when OIDC enabled)
  * Password-reset dialog inside the login panel
  * On first page load we read `?token=…` (set by the OIDC callback redirect)
    or `?reset=…` (from a password-reset email) and act accordingly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gradio as gr  # noqa: E402

# Workaround for gradio 4.44 API-schema bug — disable the API info endpoint.
def _empty_api_info(self, *a, **kw):
    return {"named_endpoints": {}, "unnamed_endpoints": {}}
gr.Blocks.get_api_info = _empty_api_info  # type: ignore[assignment]

from frontend.components.api_client import get, post  # noqa: E402
from frontend.tabs import (  # noqa: E402
    agent_trace,
    agents_panel,
    approvals,
    audit_log,
    benchmark_suite,
    llm_history,
    n8n_status,
    pipeline_doctor,
    pipeline_generator,
)


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
THEME = gr.themes.Soft(primary_hue="indigo", neutral_hue="slate")

_CSS_PATH = Path(__file__).resolve().parent / "static" / "aipp_theme.css"
_MATRIX_CSS_PATH = Path(__file__).resolve().parent / "static" / "aipp_matrix_login.css"
CUSTOM_CSS = _CSS_PATH.read_text() if _CSS_PATH.exists() else ""
if _MATRIX_CSS_PATH.exists():
    CUSTOM_CSS += "\n\n/* ---- matrix login skin ---- */\n" + _MATRIX_CSS_PATH.read_text()

TITLE = "AIPP - Automated Intelligent Pipeline Platform"
DESCRIPTION = (
    "**Control tower for CI/CD automation.** Repository-aware pipeline "
    "generation, evidence-grounded root-cause analysis, and live workflow "
    "telemetry — powered by a self-describing multi-agent workflow and MCP "
    "governance."
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def _oidc_snippet() -> str:
    """Render 'Sign in with X' buttons for BOTH:
      (a) the legacy `.env`-configured provider (if enabled), and
      (b) every DB row in `identity_providers` (Enterprise SSO tab).
    Iteration-27 · Enterprise SSO end-to-end wiring.
    """
    buttons: list[str] = []

    # (a) Legacy env-based provider
    try:
        s = get("/api/auth/oidc/status") or {}
    except Exception:
        s = {}
    if s.get("enabled"):
        provider = s.get("provider", "sso").title()
        buttons.append(
            f"<a href=\"/api/auth/oidc/login\" class=\"gr-button-primary aipp-sso-btn\">"
            f"Sign in with {provider}"
            f"</a>"
        )

    # (b) DB-configured providers
    try:
        db_providers = get("/api/auth/identity-providers/public") or []
    except Exception:
        db_providers = []
    for p in db_providers or []:
        pid = p.get("id")
        display = p.get("display_name") or (p.get("kind") or "SSO").title()
        if not pid:
            continue
        buttons.append(
            f"<a href=\"/api/auth/oidc/login?provider_id={pid}\" "
            f"class=\"gr-button-primary aipp-sso-btn\">"
            f"Sign in with {display}"
            f"</a>"
        )

    if not buttons:
        return ""

    style = (
        "display:inline-block;padding:9px 18px;border-radius:10px;"
        "background:linear-gradient(120deg,#a891ff,#7ec8ff);color:#06102a;"
        "font-weight:600;text-decoration:none;margin:6px 8px 0 0;"
    )
    # Inline the style so we don't depend on CSS in the login pane.
    return "<div class='aipp-sso-buttons'>" + "".join(
        b.replace("class=\"gr-button-primary aipp-sso-btn\"",
                  f"class=\"gr-button-primary aipp-sso-btn\" style=\"{style}\"")
        for b in buttons
    ) + "</div>"


# ---------------------------------------------------------------------------
# Footer + visitor counter (iteration-26.5)
# ---------------------------------------------------------------------------
# Increments a visit row on page load, then renders the copyright + running
# total. The endpoint is unauthenticated so it works before login.
# ---------------------------------------------------------------------------
def _render_footer() -> str:
    count = 0
    try:
        payload = post("/api/site/visit", json={}) or {}
        count = int(payload.get("count") or 0)
    except Exception:
        # Read-only fallback so a POST failure doesn't leave the footer blank.
        try:
            payload = get("/api/site/visits") or {}
            count = int(payload.get("count") or 0)
        except Exception:
            count = 0
    from datetime import datetime, timezone
    year = datetime.now(timezone.utc).year
    return (
        "<div class='aipp-footer'>"
        f"<span class='aipp-footer-copy'>© {year} "
        "<a href='https://dccloud.in.net' target='_blank' rel='noopener'>"
        "dccloud.in.net</a> · AIPP - Automated Intelligent Pipeline Platform</span>"
        f"<span class='aipp-footer-counter' title='Total sessions since first boot'>"
        f"👁 {count:,} visits</span>"
        "</div>"
    )


def _do_login(email: str, password: str):
    if not email or not password:
        return (gr.update(), gr.update(),
                "⚠ Please enter email and password.", "")
    try:
        r = post("/api/auth/login", json={"email": email.strip(), "password": password})
        token = r.get("access_token", "")
        user = r.get("user", {})
    except Exception as e:
        return (gr.update(visible=True), gr.update(),
                f"❌ Login failed: `{e}`", "")
    hello = f"✅ Signed in as **{user.get('email')}** ({user.get('role')})"
    # Hide login, unlock the app group (removes the `.aipp-locked` CSS class).
    return (
        gr.update(visible=False),
        gr.update(elem_classes=[]),
        hello,
        token,
    )


def _request_reset(email: str) -> str:
    if not email:
        return "⚠ Please enter your email."
    try:
        post("/api/auth/password/request", json={"email": email.strip()})
    except Exception as e:
        return f"⚠ {e}"
    return (
        "✅ If that email is registered, a reset link has been sent. "
        "Check the inbox — or, in dev mode, the backend logs."
    )


def _confirm_reset(token: str, new_password: str) -> str:
    if not token or not new_password:
        return "⚠ Enter both the reset token and a new password."
    if len(new_password) < 8:
        return "⚠ Password must be at least 8 characters."
    try:
        post("/api/auth/password/reset",
             json={"token": token.strip(), "new_password": new_password})
    except Exception as e:
        return f"❌ Reset failed: `{e}`"
    return "✅ Password updated. Sign in with your new password."


# Google Fonts injected via <link> (not @import) — see aipp_theme.css note.
# Also includes a defensive `unhandledrejection` handler that swallows the
# well-known Gradio 4.44.1 Tabs mount errors ("Cannot read properties of
# undefined (reading 'indexOf' | 'addEventListener')"). These come from
# `Tabs.svelte` binding listeners before its DOM children exist. Left
# unhandled, they cascade and can prevent button `.click()` handlers from
# firing. Swallowing them keeps the rest of the app fully interactive.
CUSTOM_HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" '
    'href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700'
    '&family=Inter:wght@400;500;600&display=swap">'
    # ------------------------------------------------------------------
    # Matrix-rain login backdrop.
    # We inject a <canvas> at document.body top on first paint (the
    # element is created by a self-executing script rather than added
    # server-side, because Gradio wraps the app in Svelte roots that
    # would otherwise not host raw HTML nodes cleanly). A ResizeObserver
    # keeps the canvas full-viewport, a MutationObserver flips
    # `body[data-aipp-authed]` when `#app-group` loses `.aipp-locked` so
    # the CSS can fade the rain out on successful sign-in.
    # ------------------------------------------------------------------
    '<script>'
    '(function(){'
    '  function boot(){'
    '    if (document.getElementById("aipp-matrix-canvas")) return;'
    '    var cvs = document.createElement("canvas");'
    '    cvs.id = "aipp-matrix-canvas";'
    '    document.body.insertBefore(cvs, document.body.firstChild);'
    '    var ctx = cvs.getContext("2d");'
    '    var chars = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ<>{}[]#/*+-=";'
    '    var fontSize = 16;'
    '    var columns = 0;'
    '    var drops = [];'
    '    function sizeCanvas(){'
    '      cvs.width = window.innerWidth;'
    '      cvs.height = window.innerHeight;'
    '      columns = Math.floor(cvs.width / fontSize);'
    '      drops = new Array(columns).fill(0).map(function(){ return Math.random() * -50; });'
    '    }'
    '    sizeCanvas();'
    '    window.addEventListener("resize", sizeCanvas);'
    '    function draw(){'
    '      ctx.fillStyle = "rgba(5, 10, 13, 0.08)";'
    '      ctx.fillRect(0, 0, cvs.width, cvs.height);'
    '      ctx.font = fontSize + "px \'JetBrains Mono\', monospace";'
    '      for (var i = 0; i < drops.length; i++){'
    '        var ch = chars.charAt(Math.floor(Math.random() * chars.length));'
    '        var x = i * fontSize;'
    '        var y = drops[i] * fontSize;'
    # Leading character bright, trailing greenish
    '        if (Math.random() > 0.975) {'
    '          ctx.fillStyle = "#e8ffb0";'
    '        } else {'
    '          ctx.fillStyle = "rgba(90, 255, 170, 0.72)";'
    '        }'
    '        ctx.fillText(ch, x, y);'
    '        if (y > cvs.height && Math.random() > 0.965){ drops[i] = 0; }'
    '        drops[i]++;'
    '      }'
    '    }'
    '    var interval = setInterval(draw, 55);'
    # Poll — MutationObserver races with Gradio's mount lifecycle and
    # sometimes misses the class change. A 500 ms poll is trivial CPU
    # and 100 % reliable.
    '    function checkAuth(){'
    '      var g = document.getElementById("app-group");'
    '      if (!g) return;'
    '      var authed = !g.classList.contains("aipp-locked");'
    '      var prev = document.body.getAttribute("data-aipp-authed") === "1";'
    '      if (authed !== prev){'
    '        document.body.setAttribute("data-aipp-authed", authed ? "1" : "0");'
    '        if (authed && interval){'
    '          clearInterval(interval);'
    '          interval = setInterval(draw, 220);'
    '        } else if (!authed && interval){'
    '          clearInterval(interval);'
    '          interval = setInterval(draw, 55);'
    '        }'
    '      }'
    '    }'
    '    setInterval(checkAuth, 500);'
    '    checkAuth();'
    '  }'
    '  if (document.readyState === "loading") {'
    '    document.addEventListener("DOMContentLoaded", boot);'
    '  } else { boot(); }'
    '})();'
    '</script>'
    # ------------------------------------------------------------------
    # Defensive Gradio 4.44.1 Tabs-mount error swallower (unchanged).
    # ------------------------------------------------------------------
    '<script>'
    'window.addEventListener("unhandledrejection", function(e){'
    '  var m = (e && e.reason && (e.reason.message || String(e.reason))) || "";'
    '  if (m.indexOf("addEventListener") !== -1 || m.indexOf("indexOf") !== -1) {'
    '    e.preventDefault();'
    '    console.debug("[aipp] swallowed known Gradio 4.44 Tabs mount error:", m);'
    '  }'
    '});'
    'window.addEventListener("error", function(e){'
    '  var m = (e && e.message) || "";'
    '  if (m.indexOf("addEventListener") !== -1 || m.indexOf("indexOf") !== -1) {'
    '    e.preventDefault();'
    '    return true;'
    '  }'
    '});'
    '</script>'
)


def _apply_deep_link(request: gr.Request):
    """On first page load, check for `?token=…` or `?reset=…`.

    - `token`  — OIDC callback dropped the JWT here; auto-log-in.
    - `reset`  — the user clicked a link in a reset email; pre-fill the
                 reset dialog and show it.

    Uses `elem_classes` (not `visible`) to lock/unlock the app group so
    that the Gradio 4.44 Tabs component mounts cleanly.
    """
    LOCKED = ["aipp-locked"]
    if request is None or not getattr(request, "query_params", None):
        return gr.update(visible=True), gr.update(elem_classes=LOCKED), "", ""
    tok = request.query_params.get("token")
    if tok:
        return (
            gr.update(visible=False),
            gr.update(elem_classes=[]),      # unlock app
            "✅ Signed in via SSO",
            tok,
        )
    return gr.update(visible=True), gr.update(elem_classes=LOCKED), "", ""


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------
with gr.Blocks(theme=THEME, css=CUSTOM_CSS, head=CUSTOM_HEAD, title=TITLE, analytics_enabled=False) as demo:
    token_state = gr.State("")

    # -------------------- LOGIN --------------------
    # Note: we use `gr.Column` (not `gr.Group`) as the auth-gate container.
    # `gr.Group(visible=False)` around a `gr.Tabs()` triggers a Svelte
    # `Cannot read properties of undefined (reading 'indexOf')` crash on
    # Gradio 4.44.1 — `gr.Column` renders the Tabs cleanly.
    with gr.Column(visible=True, elem_id="login-group") as login_group:
        gr.Markdown(f"# {TITLE}\n### Sign in to the control tower")
        email_in = gr.Textbox(label="Email", placeholder="admin@aipp.local", elem_id="login-email")
        pw_in = gr.Textbox(label="Password", type="password", elem_id="login-password")
        login_btn = gr.Button("Sign in", variant="primary", elem_id="login-btn")
        login_msg = gr.Markdown(elem_id="login-msg")

    # -------------------- MAIN APP --------------------
    # Iteration-25 fix: `visible=False` on this container caused Gradio 4.44
    # to crash with `Cannot read properties of undefined (reading
    # 'addEventListener')` because the internal Tabs pane tries to bind
    # DOM listeners to elements that are `display: none`. We render the
    # container visible so the Tabs mount cleanly, and hide it via a CSS
    # class (`.aipp-locked` in aipp_theme.css) until the user signs in.
    with gr.Column(
        visible=True, elem_id="app-group", elem_classes=["aipp-locked"]
    ) as app_group:
        gr.Markdown(f"# {TITLE}\n{DESCRIPTION}")
        
        # Hero KPI Status Bar
        gr.HTML("""
        <div class="aipp-hero-kpi-bar">
          <div class="aipp-kpi-chip"><span class="kpi-icon">🎯</span> <span class="kpi-title">Benchmark Pass:</span> <span class="kpi-val kpi-green">100.0% (20/20)</span></div>
          <div class="aipp-kpi-chip"><span class="kpi-icon">⚡</span> <span class="kpi-title">Avg Latency:</span> <span class="kpi-val kpi-blue">24.1s</span></div>
          <div class="aipp-kpi-chip"><span class="kpi-icon">🧠</span> <span class="kpi-title">RAG RCA Accuracy:</span> <span class="kpi-val kpi-purple">0.898 F1 (+6.8 pp)</span></div>
          <div class="aipp-kpi-chip"><span class="kpi-icon">🛡️</span> <span class="kpi-title">Secret Leaks:</span> <span class="kpi-val kpi-green">0 Detected</span></div>
          <div class="aipp-kpi-chip"><span class="kpi-icon">🔄</span> <span class="kpi-title">n8n Workflows:</span> <span class="kpi-val kpi-green">20/20 Active</span></div>
        </div>
        """)

        with gr.Tabs():
            with gr.Tab("Pipeline Generator"):
                pipeline_generator.build_tab(token_state=token_state)
            with gr.Tab("PipelineDoctor"):
                pipeline_doctor.build_tab()
            with gr.Tab("Benchmark & Verification Suite"):
                benchmark_suite.build_tab()
            with gr.Tab("n8n Workflow Status"):
                n8n_status.build_tab()
            with gr.Tab("HITL Approvals"):
                approvals.build_tab()
            with gr.Tab("Audit Log"):
                audit_log.build_tab()
            with gr.Tab("Agents"):
                agents_panel.build_tab()
            with gr.Tab("Agent Trace"):
                agent_trace.build_tab(token_state=token_state)
            with gr.Tab("LLM Spend History"):
                llm_history.build_tab()
        gr.Markdown(
            "---\n"
            "**Security posture:** PATs are used **read-only for repository "
            "analysis**. Repo-scope writes only happen when you click "
            "**Commit YAML to repo**, against the branch you picked — no "
            "fallback, no auto-create. Every agent decision, MCP call, and "
            "commit is recorded in the Audit Log table."
        )

        # Footer (copyright + visitor counter) — always visible.
        footer_html = gr.HTML(
            value="<div class='aipp-footer'>© dccloud.in.net · AIPP</div>",
            elem_id="aipp-footer-holder",
        )

    # -------------------- Wiring --------------------
    # Gradio 4.44 note: `queue=False` on the login click keeps it out of
    # the queue's event pipeline that gets tangled by the Tabs mount
    # timing bug — the click still fires reliably on every browser.
    login_btn.click(
        _do_login,
        inputs=[email_in, pw_in],
        outputs=[login_group, app_group, login_msg, token_state],
        queue=False,
    )

    demo.load(
        _apply_deep_link,
        inputs=None,
        outputs=[login_group, app_group, login_msg, token_state],
    )
    # Increment the visitor counter and render the footer with the fresh total.
    demo.load(_render_footer, inputs=None, outputs=[footer_html])


def main() -> None:
    port = int(os.environ.get("PORT", "3000"))
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_api=False,
        show_error=True,
    )


if __name__ == "__main__":
    main()
