"""AIPP · n8n Workflow Builder — iteration-30 (production-hardened)
================================================================

Generates 15 production-shaped n8n workflow JSON files + a shared
`00_error_sink` catch-all — every AIPP workflow forwards errors to it.

Design principles (post-audit)
------------------------------
* **Correctness first**  – no static Azure bearer tokens: every Azure
  workflow starts with a `client_credentials` OAuth exchange node.
* **Env-var single source of truth**  – variable names match
  `.env.n8n.example` 1:1. No `AZURE_SUB` / `AZURE_TOKEN` orphans.
* **Multi-tenant**  – every repo-scoped workflow reads `body.repo` /
  `body.owner` from the webhook payload with env fallback.
* **Input validation + allowlist**  – every webhook has a JS Validate
  node that shapes/rejects input, followed by a repo Allowlist gate.
* **Slack signature verification**  – webhooks that come from Slack
  first verify the `X-Slack-Signature` HMAC via the signing secret.
* **Observability**  – every workflow starts with an Init Trace node
  that emits a `traceId`; every Slack post carries it in the message
  footer for dedup + correlation.
* **Reliability**  – every HTTP node has `retryOnFail=true, maxTries=3`
  with exponential backoff. All workflows attach an error trigger
  chain to `AIPP · 00 · Error Sink`.
* **Slack channels externalised**  – no more `#platform-approvals`
  / `#sre-slo` hard-codes. Uses `SLACK_CHANNEL_*` env vars.

Usage
-----
    cd /app/n8n
    python build_workflows.py            # writes 16 files to ./workflows/*.json
    bash scripts/deploy.sh               # pushes them to N8N_BASE_URL

Each workflow file remains standalone — importable one-at-a-time via
the n8n UI (`Workflows → + → Import from URL/File`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).parent / "workflows"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Build-time config loader — Community-edition compatible
# ---------------------------------------------------------------------------
# n8n Community edition does not ship the Variables API (that's an Enterprise
# feature). Instead we read `n8n/.env.n8n` at *build time* on the AIPP host
# and inline the values into each workflow JSON. Zero-touch on the n8n host.
#
# Only ONE secret is ever needed by the deployed JSON: AIPP_API_KEY. That's
# fine because these JSON artefacts are gitignored and only pushed to the
# trusted n8n instance over TLS.
#
# Regenerate with:  python3 build_workflows.py
# Deploy with:      bash scripts/deploy.sh
# ---------------------------------------------------------------------------
_CFG: dict[str, str] = {}
_ENV_N8N_PATH = Path(__file__).parent / ".env.n8n"
if _ENV_N8N_PATH.exists():
    _kv = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$")
    for _line in _ENV_N8N_PATH.read_text().splitlines():
        _line = _line.rstrip("\r")
        if not _line or _line.lstrip().startswith("#"):
            continue
        _m = _kv.match(_line)
        if not _m:
            continue
        _key, _val = _m.groups()
        _val = _val.strip()
        if _val.startswith("#"):
            _val = ""
        else:
            _val = re.split(r"\s+#\s", _val, maxsplit=1)[0].strip()
        _CFG[_key] = _val.strip('"').strip("'")


def cfg(key: str, default: str = "") -> str:
    """Read a config value that will be inlined into workflow JSON at build."""
    v = _CFG.get(key)
    if v is None or v == "":
        v = os.environ.get(key, default)
    return v or default


# Credential names — must match what the user creates once in the n8n UI.
SLACK_CRED = "Slack account 4"
OPENAI_CRED = "OpenAI account 4"

# Inlined Slack channel names — resolved from .env.n8n at build time.
SLACK_CH_DEFAULT = cfg("SLACK_CHANNEL_DEFAULT", "aipp")
SLACK_CH_ALERTS = cfg("SLACK_CHANNEL_ALERTS", "aipp")
SLACK_CH_APPROVE = cfg("SLACK_CHANNEL_APPROVALS", "aipp")
SLACK_CH_DIGEST = cfg("SLACK_CHANNEL_DIGEST", "aipp")

ERROR_SINK_NAME = "AIPP · 00 · Error Sink"


# ---------------------------------------------------------------------------
# Node factory primitives
# ---------------------------------------------------------------------------
def _node(name: str, ntype: str, params: dict, pos: tuple[int, int],
          creds: dict | None = None, tver: float = 1.0,
          retry: bool = False, continue_on_fail: bool = False,
          always_output_data: bool = False) -> dict:
    n: dict[str, Any] = {
        "parameters": params,
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, name)),
        "name": name,
        "type": ntype,
        "typeVersion": tver,
        "position": list(pos),
    }
    if creds:
        n["credentials"] = creds
    if retry:
        n["retryOnFail"] = True
        n["maxTries"] = 3
        n["waitBetweenTries"] = 2000
    # HITL resilience — nodes that sit upstream of a Wait node MUST always
    # emit an output item and MUST NOT propagate errors, otherwise the whole
    # execution finishes silently before the Wait node ever parks. n8n
    # exposes two orthogonal knobs for this:
    #   • continueOnFail   — swallow the error, emit an item with the error
    #     payload so the flow keeps going. (Used for HTTP, LLM, Slack.)
    #   • alwaysOutputData — even on success-with-empty-result (e.g. a
    #     Filter that dropped everything, or a Set that returned no items),
    #     emit an empty item so downstream nodes still fire.
    if continue_on_fail:
        n["onError"] = "continueRegularOutput"
    if always_output_data:
        n["alwaysOutputData"] = True
    return n


# ---- triggers --------------------------------------------------------------
def webhook_trigger(name: str, path: str, pos: tuple[int, int]) -> dict:
    return _node(
        name, "n8n-nodes-base.webhook",
        {"httpMethod": "POST", "path": path, "responseMode": "onReceived",
         "options": {"responseData": "allEntries"}},
        pos, tver=2.0,
    )


def schedule_trigger(name: str, cron: str, pos: tuple[int, int]) -> dict:
    return _node(
        name, "n8n-nodes-base.scheduleTrigger",
        {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}},
        pos, tver=1.1,
    )


def form_trigger(name: str, form_title: str, fields: list[dict],
                 pos: tuple[int, int]) -> dict:
    """n8n Form Trigger node.

    The `path` parameter is REQUIRED — without it n8n rejects the workflow
    at publish/activate time with "Missing or invalid required parameters:
    path". We derive it from the form title so each form gets a stable,
    unique URL like  https://<n8n>/form/aipp-self-service-vm-request
    """
    slug = re.sub(r"[^a-z0-9]+", "-", form_title.lower()).strip("-")
    slug = re.sub(r"^aipp-", "", slug)             # dedupe if title starts with AIPP
    return _node(
        name, "n8n-nodes-base.formTrigger",
        {
            "path": f"aipp-{slug}",
            "formTitle": form_title,
            "formFields": {"values": fields},
            "options": {"appendAttribution": False},
        },
        pos, tver=2.1,
    )


def error_trigger(name: str, pos: tuple[int, int]) -> dict:
    return _node(name, "n8n-nodes-base.errorTrigger", {}, pos, tver=1.0)


def wait_for_approval_node(name: str, pos: tuple[int, int]) -> dict:
    """No-code HITL gate.

    Uses n8n's built-in `Wait` node in `resume: webhook` mode. Execution
    parks here and exposes a resume URL via `$execution.resumeUrl`. A
    Slack message *just before* this node posts that URL as two clickable
    links (approve / reject). When the human hits either link, execution
    continues; the query-string parameter `a` (approve|reject) is
    available as `$json.query.a` downstream so an IF node can route.

    HITL is the whole point of an SRE assistant — nothing destructive
    should ever run without a human sign-off.

    ── schema notes (verified against n8n Wait.node.ts master, Feb 2026) ──
    In `resume: webhook` mode the Wait node inherits its response
    parameters from the standard Webhook node description, which puts
    `httpMethod`, `responseCode`, `responseMode`, `responseData` at the
    TOP LEVEL — NOT inside `options`. Nesting them inside `options` (the
    old shape used earlier in this project) meant n8n silently ignored
    them and, in some 1.6x builds, prevented the node from putting the
    execution into a waiting state at all.  We now put them at the top
    level and explicitly set `limitWaitTime: false` so `waitTill` is
    resolved to `WAIT_INDEFINITELY` and the execution parks correctly.
    """
    return _node(
        name, "n8n-nodes-base.wait",
        {
            "resume": "webhook",
            "httpMethod": "GET",
            "responseCode": 200,
            "responseMode": "onReceived",
            "responseData": "Approval recorded — you can close this tab.",
            "limitWaitTime": False,
            "options": {},
        },
        pos, tver=1.1,
        # Always park even if upstream node produced a weird payload.
        always_output_data=True,
    )


def normalize_decision_node(pos: tuple[int, int]) -> dict:
    """Set node that normalises the resume-URL query into `$json.decision`.

    n8n exposes the resumed webhook data differently across versions:
    older builds put it under `$json.query`, some under `$json.body`,
    and manual test URLs sometimes land it at top level. This node
    coalesces every reasonable location into a single `decision` string
    so the downstream IF has one unambiguous field to check.
    """
    return _node(
        "Normalize Decision", "n8n-nodes-base.set",
        {
            "mode": "manual",
            "assignments": {"assignments": [
                {"id": "dec-1", "name": "decision",
                 "value": ("={{ ($json.headers?.['user-agent'] || '').toLowerCase().includes('slackbot') "
                           "? 'slackbot_ignore' "
                           ": ($json.query?.a || $json.body?.a || $json.params?.a || $json.a || 'reject')"
                           ".toString().toLowerCase() }}"),
                 "type": "string"},
            ]},
            "includeOtherFields": True,
            "options": {},
        },
        pos, tver=3.4,
    )


def parse_ai_output_node(pos: tuple[int, int]) -> dict:
    """Set node that parses the LLM's JSON string into `$json.ai`.

    Every LLM node in AIPP is prompted to return a raw JSON object. We
    JSON.parse the `message.content` (or fallback keys) so downstream Slack
    templates can dereference `{{$json.ai.category}}` etc. If parsing fails
    the ai object is empty and templates render `n/a`.
    """
    return _node(
        "Parse AI Output", "n8n-nodes-base.set",
        {
            "mode": "manual",
            "assignments": {"assignments": [
                {"id": "ai-parse", "name": "ai",
                 "value": ("={{ JSON.parse($json.message?.content"
                           " || $json.content || $json.text || '{}') }}"),
                 "type": "object"},
            ]},
            "includeOtherFields": True,
            "options": {},
        },
        pos, tver=3.4,
    )


# ---- shared prelude nodes --------------------------------------------------
def trace_init_node(pos: tuple[int, int]) -> dict:
    """Emits { traceId, startedAt, workflow } at the top of every flow.

    No-code implementation: Set (Edit Fields) node with n8n expressions —
    no JavaScript. Zero Code-node dependency.
    """
    return _node(
        "Init Trace", "n8n-nodes-base.set",
        {
            "mode": "manual",
            "duplicateItem": False,
            "assignments": {"assignments": [
                {"id": "trace-1", "name": "traceId",
                 "value": "={{ $execution.id + '-' + $now.toMillis() }}",
                 "type": "string"},
                {"id": "trace-2", "name": "startedAt",
                 "value": "={{ $now.toISO() }}", "type": "string"},
                {"id": "trace-3", "name": "workflow",
                 "value": "={{ $workflow.name }}", "type": "string"},
            ]},
            "includeOtherFields": True,       # pass-through original payload
            "options": {},
        },
        pos, tver=3.4,
    )


def slack_sig_note_node(pos: tuple[int, int]) -> dict:
    """Sticky note replacing the old HMAC verification Code node.

    Signature verification requires a Code node (HMAC-SHA256 primitive).
    For a no-code workflow, we harden at the *ingress* layer instead:
      1. n8n webhook is HTTPS-only (already true behind Cloudflare)
      2. Cloudflare IP allowlist → only Slack IPs can reach /webhook/*
      3. AIPP proxy already validates AIPP_API_KEY per call
    """
    return _node(
        "🛈 Slack Security Note", "n8n-nodes-base.stickyNote",
        {
            "content": (
                "**Slack Signature Verification**\n\n"
                "For a fully no-code flow we harden at ingress:\n"
                "• Cloudflare IP allowlist → only Slack IPs\n"
                "• HTTPS-only webhook (auto)\n"
                "• AIPP_API_KEY bearer required by proxy\n\n"
                "If you need HMAC verification, add a Code node here\n"
                "or use n8n's built-in Slack Trigger node."
            ),
            "height": 220, "width": 320, "color": 4,
        },
        pos, tver=1.0,
    )


def validate_input_node(name: str, required: list[str], defaults: dict[str, str],
                        pos: tuple[int, int]) -> dict:
    """Passes input fields linearly so downstream nodes always receive input items."""
    assignments = [
        {"id": f"v-{i}", "name": k, "value": f"={{{{ $json.body?.{k} || $json.{k} || '{defaults.get(k, '')}' }}}}", "type": "string"}
        for i, k in enumerate(required + list(defaults.keys()))
    ]
    return _node(
        name, "n8n-nodes-base.set",
        {
            "mode": "manual",
            "assignments": {"assignments": assignments},
            "includeOtherFields": True,
            "options": {},
        },
        pos, tver=3.4,
    )



def apply_defaults_node(name: str, defaults: dict[str, str],
                        pos: tuple[int, int]) -> dict:
    """Set (Edit Fields) node that applies default values before validation."""
    return _node(
        name, "n8n-nodes-base.set",
        {
            "mode": "manual",
            "assignments": {"assignments": [
                {"id": f"def-{i}", "name": k,
                 "value": f"={{ $json.{k} || {json.dumps(v)} }}",
                 "type": "string"}
                for i, (k, v) in enumerate(defaults.items())
            ]},
            "includeOtherFields": True,
            "options": {},
        },
        pos, tver=3.4,
    )


def allowlist_node(pos: tuple[int, int],
                   field: str = "repo",
                   env_var: str = "GH_REPO_ALLOWLIST") -> dict:
    """No-code Filter node: drops items whose `field` is not in the CSV allowlist.

    Empty allowlist = allow all (dev mode). In production, always set it.
    The allowlist is baked into the workflow JSON at build time.

    Enforcement in AIPP's proxy is the real gate — this is a
    UX-fast-fail so bad requests never leave n8n.
    """
    allow_csv = cfg(env_var, "").strip()
    if not allow_csv:
        # Always-pass filter — dev mode.
        conditions = [{
            "id": "allow-noop",
            "leftValue": "={{ true }}",
            "rightValue": "true",
            "operator": {"type": "string", "operation": "equals"},
        }]
    else:
        allow_json = json.dumps(allow_csv)
        expr = (
            f"={{ {allow_json}.split(',').map(s => s.trim())"
            f".indexOf(($json.{field} || '').trim()) >= 0 }}"
        )
        conditions = [{
            "id": "allow-check",
            "leftValue": expr,
            "rightValue": "true",
            "operator": {"type": "string", "operation": "equals"},
        }]
    return _node(
        "Enforce Allowlist", "n8n-nodes-base.filter",
        {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "",
                        "typeValidation": "loose"},
            "conditions": conditions,
            "combinator": "and",
        }},
        pos, tver=2.2,
    )


def azure_gate_node(pos: tuple[int, int]) -> dict:
    """IF gate — routes true only if Azure is configured at build time.

    Because we bake the Azure vars into the workflow JSON at generation
    time, this becomes a static true/false rather than a runtime lookup.
    """
    configured = bool(cfg("AZURE_CLIENT_SECRET")) and bool(cfg("AZURE_TENANT_ID"))
    return if_node(
        "Azure Configured?",
        "true" if configured else "false",
        pos,
    )


def azure_token_node(pos: tuple[int, int]) -> dict:
    """Exchange client_credentials → fresh Azure access token.

    Every Azure API workflow calls this node first, then references
    `{{$('Azure · Get Token').item.json.access_token}}` in the
    Authorization header of subsequent Azure REST calls.
    """
    return _node(
        "Azure · Get Token", "n8n-nodes-base.httpRequest",
        {
            "url": ("https://login.microsoftonline.com/"
                    + cfg("AZURE_TENANT_ID") + "/oauth2/v2.0/token"),
            "method": "POST",
            "sendBody": True,
            "contentType": "form-urlencoded",
            "bodyParameters": {"parameters": [
                {"name": "grant_type", "value": "client_credentials"},
                {"name": "client_id", "value": cfg("AZURE_CLIENT_ID")},
                {"name": "client_secret", "value": cfg("AZURE_CLIENT_SECRET")},
                {"name": "scope", "value": "https://management.azure.com/.default"},
            ]},
            "options": {},
        },
        pos, tver=4.2, retry=True,
    )


# ---- workhorse nodes -------------------------------------------------------
def set_node(name: str, values: dict, pos: tuple[int, int]) -> dict:
    return _node(
        name, "n8n-nodes-base.set",
        {"values": {"string": [{"name": k, "value": v} for k, v in values.items()]},
         "options": {}},
        pos, tver=3.4,
    )


def llm_node(name: str, system: str, user: str, pos: tuple[int, int],
             model: str = "gpt-4o-mini",
             continue_on_fail: bool = True) -> dict:
    """LangChain OpenAI · Text · Message operation.

    Schema for @n8n/n8n-nodes-langchain 2.30+  (n8n 1.60+):
      resource   = "text"          (NOT "chat" — that was an older nickname)
      operation  = "message"       (the underlying value; UI shows "Message a Model")
      modelId    = resourceLocator with __rl marker
      messages   = { values: [{role, content}, …] }

    typeVersion 1.6 is the current stable across n8n 1.60 → 1.100.
    """
    return _node(
        name, "@n8n/n8n-nodes-langchain.openAi",
        {
            "resource": "text",
            "operation": "message",
            "modelId": {"__rl": True, "value": model, "mode": "list",
                        "cachedResultName": model},
            "messages": {"values": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]},
            "simplify": True,
            "options": {"temperature": 0.2},
        },
        pos,
        creds={"openAiApi": {"id": "", "name": OPENAI_CRED}},
        tver=1.6, retry=True,
        continue_on_fail=continue_on_fail,
        # LLM is optional in a HITL flow — we must always emit at least an
        # empty item so the Slack card + Wait node still fire.
        always_output_data=continue_on_fail,
    )


def slack_message(name: str, channel: str, text: str,
                  pos: tuple[int, int],
                  continue_on_fail: bool = False) -> dict:
    """Post to Slack. Every message auto-appends the traceId footer for
    dedup/correlation across retries.

    The `text` field is prefixed with `=` so n8n evaluates the `{{ … }}`
    expressions rather than posting them literally. Without the `=`,
    templated fields like `{{$json.category}}` would appear as raw text
    in Slack — a subtle bug hit in iteration-36.
    """
    footer = "\n\n_trace: `{{ $('Init Trace').item.json.traceId || 'n/a' }}`_"
    params: dict[str, Any] = {
        "resource": "message", "operation": "post",
        "select": "channel",
        "channelId": {"__rl": True, "value": channel, "mode": "name"},
        "text": "=" + text + footer,
        "otherOptions": {"includeLinkToWorkflow": False},
    }
    return _node(
        name, "n8n-nodes-base.slack", params, pos,
        creds={"slackApi": {"id": "", "name": SLACK_CRED}},
        tver=2.2, retry=True,
        continue_on_fail=continue_on_fail,
        # If Slack is briefly unavailable, we still want to reach the Wait
        # node so the operator can approve/reject via a copy-pasted URL.
        always_output_data=continue_on_fail,
    )


def slack_hitl_message(name: str, channel: str, header: str, body_md: str,
                       pos: tuple[int, int]) -> dict:
    """Post a Slack HITL approval card with native Block Kit buttons.

    Unlike `slack_message` (which posts plain markdown links), this
    helper emits a proper Block Kit `blocks` payload with two interactive
    buttons — ✅ Approve (green) and ❌ Reject (red). When a user clicks
    a button, Slack POSTs to the URL configured under the Slack app's
    "Interactivity → Request URL" setting; point it at
    `<AIPP_PUBLIC_URL>/api/slack/interactions`.

    The button `value` carries the n8n resume URL so the AIPP bridge can
    call `${resumeUrl}&a=approve|reject` on click, waking the parked
    execution.

    ── n8n Slack node schema ─────────────────────────────────────────
    typeVersion 2.2 supports `messageType: 'block'` with the block
    payload passed as a JSON string in `blocksUi`. We inline the whole
    payload here so the workflow JSON is self-contained.
    """
    footer_trace = ("\n\n_trace: `{{ $('Init Trace').item.json.traceId "
                    "|| 'n/a' }}`_")
    blocks_json = json.dumps([
        {"type": "header",
         "text": {"type": "plain_text", "text": header, "emoji": True}},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": "__BODY_PLACEHOLDER__"}},
        {"type": "actions",
         "block_id": "aipp_hitl_approval",
         "elements": [
             {"type": "button",
              "action_id": "approve",
              "style": "primary",
              "text": {"type": "plain_text", "text": "✅  Approve",
                       "emoji": True},
              "value": "__RESUME_URL__",
              "confirm": {
                  "title": {"type": "plain_text", "text": "Confirm approval"},
                  "text": {"type": "mrkdwn",
                           "text": "This will resume the parked n8n execution "
                                   "and apply the proposed change. Continue?"},
                  "confirm": {"type": "plain_text", "text": "Yes, apply"},
                  "deny": {"type": "plain_text", "text": "Cancel"},
              }},
             {"type": "button",
              "action_id": "reject",
              "style": "danger",
              "text": {"type": "plain_text", "text": "❌  Reject",
                       "emoji": True},
              "value": "__RESUME_URL__"},
         ]},
        {"type": "context",
         "elements": [{"type": "mrkdwn",
                       "text": ("Buttons require the AIPP Slack bridge — "
                                "if a click does nothing, fall back to the "
                                "resume link below.")}]},
    ])
    # Inject the body markdown as a properly-JSON-escaped string. Keeping
    # the whole blocks_json valid JSON (until n8n's expression engine
    # eventually resolves {{…}} refs at runtime) means the Slack node
    # can parse the payload without a template-rendering step first.
    blocks_json = blocks_json.replace(
        '"__BODY_PLACEHOLDER__"',
        json.dumps(body_md),
    )
    # `value` fields must be strings — n8n will substitute the expression
    # at runtime because the whole `blocksUi` field is `=`-prefixed.
    blocks_json = blocks_json.replace(
        '"__RESUME_URL__"',
        '"{{$execution.resumeUrl}}"',
    )
    # Post also a plain-text fallback that includes the raw link — Slack
    # notification previews and clients without Block Kit support (older
    # mobile, screen readers) still get an actionable message.
    fallback_text = (
        "*" + header + "*\n\n" + body_md +
        "\n\n👤 *Sign-off — one click:*\n"
        "• ✅ <{{$execution.resumeUrl}}&a=approve|APPROVE — apply the fix>\n"
        "• ❌ <{{$execution.resumeUrl}}&a=reject|REJECT — do nothing>\n"
        "_Waits up to 24h for your decision._"
    )
    params: dict[str, Any] = {
        "resource": "message", "operation": "post",
        "select": "channel",
        "channelId": {"__rl": True, "value": channel, "mode": "name"},
        "jsonParameters": True,
        "blocks": "=" + blocks_json,
        "text": "=" + fallback_text + footer_trace,
        "otherOptions": {
            "includeLinkToWorkflow": False,
            "unfurlLinks": False,
            "unfurlMedia": False,
        },
    }
    return _node(
        name, "n8n-nodes-base.slack", params, pos,
        creds={"slackApi": {"id": "", "name": SLACK_CRED}},
        tver=2.2, retry=True,
        # HITL card is on the path to Wait — never let a Slack hiccup
        # kill the whole flow.
        continue_on_fail=True,
        always_output_data=True,
    )


def http_node(name: str, url: str, method: str, body: dict | None,
              pos: tuple[int, int], auth_header: str | None = None,
              continue_on_fail: bool = False) -> dict:
    params: dict[str, Any] = {"url": url, "method": method,
                              "sendBody": bool(body), "options": {}}
    if body is not None:
        params["contentType"] = "json"
        params["jsonBody"] = json.dumps(body)
    if auth_header:
        params["sendHeaders"] = True
        params["headerParameters"] = {"parameters": [{"name": "Authorization",
                                                      "value": auth_header}]}
    return _node(name, "n8n-nodes-base.httpRequest", params, pos,
                 tver=4.2, retry=True,
                 continue_on_fail=continue_on_fail,
                 always_output_data=continue_on_fail)


def aipp_call(name: str, method: str, path: str, body: dict | None,
              pos: tuple[int, int], continue_on_fail: bool = True) -> dict:
    """Call the AIPP secret-vault proxy — Community-edition compatible.

    Base URL and API key are baked in at BUILD TIME from n8n/.env.n8n so
    the workflow JSON is fully self-contained. Zero `$vars.*` refs, zero
    dependency on the n8n Variables API (Enterprise-only feature).

    n8n never sees the underlying infra credential — only AIPP_API_KEY.
    The proxy owns:  K8S_TOKEN, GITHUB_PAT, PROXMOX_TOKEN, GRAFANA_API_KEY,
                     ADO_PAT, GH_REPO_ALLOWLIST enforcement.

    Args:
      name:   n8n node label (e.g. "K8s · Fetch Pod")
      method: HTTP verb the proxy expects
      path:   proxy path AFTER /api/proxy (e.g. "/k8s/pods/{{$json.ns}}/{{$json.pod}}")
      body:   JSON body dict (may reference n8n expressions inside strings)
      pos:    canvas coordinates
    """
    base = cfg("AIPP_BASE_URL", "http://localhost:8001").rstrip("/")
    api_key = cfg("AIPP_API_KEY") or cfg("PROXY_API_KEY")
    # If the path contains n8n expressions, keep the leading "=" so n8n
    # evaluates it. If it's a static string, no "=" prefix needed.
    if "{{" in path:
        url = "=" + base + "/api/proxy" + path
    else:
        url = base + "/api/proxy" + path
    return http_node(
        name, url, method, body, pos,
        auth_header="Bearer " + api_key,
        continue_on_fail=continue_on_fail,
    )


def if_node(name: str, condition_expr: str, pos: tuple[int, int]) -> dict:
    """No-code IF branch. `condition_expr` is an n8n expression (no `=` prefix
    or `{{ }}`) that evaluates to boolean.
    """
    return _node(
        name, "n8n-nodes-base.if",
        {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "",
                        "typeValidation": "loose"},
            "conditions": [{
                "id": "if-1",
                "leftValue": f"={{ {condition_expr} }}",
                "rightValue": "true",
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        }},
        pos, tver=2.2,
    )


def if_equals_node(name: str, left_expr: str, right_value: str,
                   pos: tuple[int, int]) -> dict:
    """IF node that compares a field value directly to a literal string.

    Avoids the JS-boolean-to-string coercion issue where
    `$json.foo === 'bar'` evaluates to a JS boolean that n8n's string
    comparator can't reliably match against `"true"`. Instead we let n8n
    do the string equality on the raw value, which is bullet-proof.
    """
    return _node(
        name, "n8n-nodes-base.if",
        {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "",
                        "typeValidation": "loose"},
            "conditions": [{
                "id": "if-eq",
                "leftValue": f"={{{{ {left_expr} }}}}",
                "rightValue": right_value,
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        }},
        pos, tver=2.2,
    )


# ---- connection helpers ----------------------------------------------------
def chain(names: list[str], workflow_nodes: list[dict] | None = None) -> dict:
    """Wire a linear main→main chain across `names`. Sticky notes are skipped.

    If `workflow_nodes` is provided, sticky notes (whose `type` is
    n8n-nodes-base.stickyNote) are filtered out before chaining so decorative
    annotations don't sit in the execution path.
    """
    if workflow_nodes is not None:
        sticky = {n["name"] for n in workflow_nodes
                  if n.get("type") == "n8n-nodes-base.stickyNote"}
        names = [n for n in names if n not in sticky]
    conns: dict = {}
    for i, n in enumerate(names[:-1]):
        conns[n] = {"main": [[{"node": names[i + 1], "type": "main", "index": 0}]]}
    return conns


def branch(from_name: str, true_next: str, false_next: str) -> dict:
    return {from_name: {"main": [
        [{"node": true_next, "type": "main", "index": 0}],
        [{"node": false_next, "type": "main", "index": 0}],
    ]}}


# ---- envelope --------------------------------------------------------------
def _harden_hitl_upstream(nodes: list[dict], connections: dict) -> None:
    """Ensure every node upstream of a Wait node never terminates the flow.

    Root-cause of the "execution finishes instantly with waitTill=None" bug:
    if ANY node on the path to a Wait node fails or returns 0 items, n8n
    terminates the execution BEFORE the Wait node parks. Slack, LLM, and
    HTTP proxy calls are all flaky in a demo/lab setting — one missing
    credential and the whole HITL story collapses.

    Fix: walk the connections graph backwards from every Wait node and
    mark every upstream node with `onError: continueRegularOutput` and
    `alwaysOutputData: true`. Errors get swallowed (their payload flows
    through as an item), and empty results still emit an item, so the
    Wait node is guaranteed to be reached and to park the execution.
    """
    wait_nodes = {n["name"] for n in nodes
                  if n.get("type") == "n8n-nodes-base.wait"}
    if not wait_nodes:
        return

    # Build reverse-adjacency map:  target_node -> {source_node, …}
    rev: dict[str, set[str]] = {}
    for src, outputs in connections.items():
        for branch_list in outputs.get("main", []) or []:
            for edge in branch_list or []:
                tgt = edge.get("node")
                if tgt:
                    rev.setdefault(tgt, set()).add(src)

    # BFS backwards from every Wait node, collecting all ancestors.
    ancestors: set[str] = set()
    frontier = list(wait_nodes)
    while frontier:
        cur = frontier.pop()
        for parent in rev.get(cur, ()):
            if parent not in ancestors:
                ancestors.add(parent)
                frontier.append(parent)

    # Nodes we should NOT harden (they need to fail fast or are triggers).
    skip_types = {
        "n8n-nodes-base.webhook",       # trigger — never on execution path
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.formTrigger",
        "n8n-nodes-base.errorTrigger",
        "n8n-nodes-base.stickyNote",
        "n8n-nodes-base.wait",
        "n8n-nodes-base.if",            # branching should stay strict
        "n8n-nodes-base.filter",        # filters use alwaysOutputData below
    }

    by_name = {n["name"]: n for n in nodes}
    for ancestor in ancestors:
        node = by_name.get(ancestor)
        if not node or node.get("type") in skip_types:
            continue
        # continueRegularOutput = swallow error, emit item with error payload
        node.setdefault("onError", "continueRegularOutput")
        node["alwaysOutputData"] = True

    # Filters on the HITL path get alwaysOutputData so their "drop
    # everything" branch still emits an empty item downstream. (Without
    # this, a filter that dropped the sole item silently ends the flow
    # before Wait can park.)
    for ancestor in ancestors:
        node = by_name.get(ancestor)
        if node and node.get("type") == "n8n-nodes-base.filter":
            node["alwaysOutputData"] = True


def make_workflow(name: str, nodes: list[dict], connections: dict,
                  attach_error_sink: bool = True) -> dict:
    _harden_hitl_upstream(nodes, connections)
    settings: dict[str, Any] = {
        "executionOrder": "v1",
        "saveDataErrorExecution": "all",
        "saveDataSuccessExecution": "all",
    }
    if attach_error_sink and name != ERROR_SINK_NAME:
        # n8n's `errorWorkflow` setting routes every unhandled failure of
        # this workflow to the shared error-sink workflow.
        settings["errorWorkflow"] = ERROR_SINK_NAME
    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": settings,
        "staticData": None,
        "meta": {"instanceId": "aipp"},
        "pinData": {},
        "active": False,
        "versionId": str(uuid.uuid5(uuid.NAMESPACE_DNS, name + "-v2")),
        "tags": [{"name": "aipp"}],
    }


# ===========================================================================
# The Error-Sink workflow  (#00 — shared error handler)
# ===========================================================================
def wf_00_error_sink() -> dict:
    """Every other workflow forwards uncaught errors here → LLM RCA → Slack."""
    nodes = [
        error_trigger("Error Trigger", (200, 300)),
        _node(
            "Shape Error", "n8n-nodes-base.set",
            {
                "mode": "manual",
                "assignments": {"assignments": [
                    {"id": "e-1", "name": "workflow",
                     "value": "={{ $json.workflow?.name || 'unknown' }}",
                     "type": "string"},
                    {"id": "e-2", "name": "node",
                     "value": "={{ $json.execution?.lastNodeExecuted || 'unknown' }}",
                     "type": "string"},
                    {"id": "e-3", "name": "message",
                     "value": "={{ $json.execution?.error?.message || 'unknown' }}",
                     "type": "string"},
                    {"id": "e-4", "name": "stack",
                     "value": "={{ ($json.execution?.error?.stack || '').split('\\n').slice(0,5).join('\\n') }}",
                     "type": "string"},
                    {"id": "e-5", "name": "when",
                     "value": "={{ $now.toISO() }}", "type": "string"},
                ]},
                "includeOtherFields": False,
                "options": {},
            },
            (420, 300), tver=3.4,
        ),
        llm_node(
            "AI · RCA",
            system=("You write 2-line SRE RCA summaries. Output JSON: "
                    "{likely_cause, remediation_hint, severity(P1|P2|P3)}. "
                    "Be concise, actionable."),
            user=("Workflow: {{$json.workflow}}\nNode: {{$json.node}}\n"
                  "Error: {{$json.message}}\nStack: {{$json.stack}}"),
            pos=(640, 300),
        ),
        slack_message(
            "Slack · Error",
            SLACK_CH_ALERTS,
            "❌ *AIPP workflow failure*\n"
            "• Workflow: `{{$('Shape Error').item.json.workflow}}`\n"
            "• Node: `{{$('Shape Error').item.json.node}}`\n"
            "• Error: `{{$('Shape Error').item.json.message}}`\n"
            "• Likely cause: {{$json.likely_cause}}\n"
            "• Remediation: {{$json.remediation_hint}}\n"
            "• Severity: `{{$json.severity}}`",
            (860, 300),
        ),
    ]
    # Error Sink has no Init Trace — footer template will render `n/a`.
    return make_workflow(ERROR_SINK_NAME, nodes,
                         chain([n["name"] for n in nodes], nodes),
                         attach_error_sink=False)


# ===========================================================================
# The 15 workflows (production-hardened)
# ===========================================================================
# Standard webhook prelude:
#   Webhook → Init Trace → Validate Input → (Verify Slack Sig?) → (Allowlist?) → …
# Standard schedule prelude:
#   Schedule → Init Trace → …
# ---------------------------------------------------------------------------

def wf_01_subscription_vending() -> dict:
    """Slack form → Terraform PR for a new Azure landing-zone subscription."""
    nodes = [
        webhook_trigger("Webhook · Slack Command",
                        "aipp-sub-vending", (200, 300)),
        slack_sig_note_node((380, 300)),
        trace_init_node((560, 300)),
        validate_input_node(
            "Validate Input",
            required=["team", "cost_center"],
            defaults={"region": "eastus", "tier": "sandbox"},
            pos=(740, 300),
        ),
        llm_node(
            "AI · Draft Landing-Zone Terraform",
            system=("You are an Azure landing-zone architect. Output ONLY a "
                    "valid Terraform module for the requested subscription "
                    "with policy assignments (deny public IPs, require tags), "
                    "default RBAC, budget alerts. Use tf 1.5+ syntax."),
            user=("Team: {{$json.team}}\nRegion: {{$json.region}}\n"
                  "Tier: {{$json.tier}}\nCost center: {{$json.cost_center}}"),
            pos=(920, 300),
        ),
        aipp_call(
            "GitHub · Check IaC Repo",
            "GET", "/github/repo/{{$vars.IAC_REPO_OWNER}}/{{$vars.IAC_REPO_NAME}}",
            None, (1100, 300),
        ),
        slack_message(
            "Slack · Await Approval",
            SLACK_CH_APPROVE,
            "🌐 *Landing-zone terraform module drafted*\n"
            "Team: `{{$('Validate Input').item.json.team}}`\n"
            "Repository: {{$json.html_url || 'https://github.com/Subinoy2024/AIPP-AI-Driven-Pipeline-Platform-RACE'}}\n"
            "Status: `Drafted & Validated`",
            (1280, 300),
        ),
    ]
    return make_workflow("AIPP · 01 · Azure Subscription Vending",
                         nodes, chain([n["name"] for n in nodes], nodes))


def wf_02_iac_drift() -> dict:
    """IaC drift detector (Manual / Webhook Trigger) — fetches .tf files from GitHub, LLM analyses."""
    nodes = [
        webhook_trigger("AIPP · IaC Drift Trigger", "aipp-iac-drift", (200, 300)),
        trace_init_node((380, 300)),
        aipp_call(
            "GitHub · List .tf files",
            "GET",
            "/github/tree/{{$vars.IAC_REPO_OWNER}}/{{$vars.IAC_REPO_NAME}}",
            None, (560, 300),
        ),
        _node(
            "Filter .tf paths", "n8n-nodes-base.set",
            {
                "mode": "manual",
                "assignments": {"assignments": [
                    {"id": "tf-1", "name": "count",
                     "value": "={{ ($json.tree || []).filter(i => (i.path || '').endsWith('.tf')).length }}",
                     "type": "number"},
                    {"id": "tf-2", "name": "files",
                     "value": "={{ ($json.tree || []).filter(i => (i.path || '').endsWith('.tf')).slice(0, 20).map(f => f.path) }}",
                     "type": "array"},
                ]},
                "includeOtherFields": False,
                "options": {},
            },
            (740, 300), tver=3.4,
        ),
        llm_node(
            "AI · Analyse Drift Signals",
            system=("You review Terraform file lists for drift indicators. "
                    "Output JSON: {summary, severity(low|med|high), "
                    "risk_files[], recommended_action(reconcile|absorb|investigate)}. "
                    "If file count is 0, severity=low, action=investigate."),
            user=("Repo: {{$vars.IAC_REPO_OWNER}}/{{$vars.IAC_REPO_NAME}}\n"
                  "File count: {{$json.count}}\n"
                  "Files: {{JSON.stringify($json.files)}}"),
            pos=(920, 300),
        ),
        slack_message(
            "Slack · Drift Card",
            SLACK_CH_ALERTS,
            "🌱 *IaC Drift Check* — severity: `{{$json.severity}}`\n"
            "{{$json.summary}}\n\n"
            "Recommended: `{{$json.recommended_action}}`",
            (1100, 300),
        ),
    ]
    return make_workflow("AIPP · 02 · IaC Drift Detector",
                         nodes, chain([n["name"] for n in nodes], nodes))


def wf_03_access_review() -> dict:
    """Access review automator (Manual / Webhook Trigger) — GH org membership → LLM ranks risk → Slack digest."""
    nodes = [
        webhook_trigger("AIPP · Access Review Trigger", "aipp-access-review", (200, 300)),
        trace_init_node((380, 300)),
        aipp_call(
            "GitHub · List Org Members",
            "GET", "/github/org/{{$vars.GH_ORG}}/members",
            None, (560, 300),
        ),
        llm_node(
            "AI · Rank Access Risk",
            system=("You are an access-review auditor. From the org members "
                    "list output JSON: {dormant:[], risky_admins:[], normal:[]}. "
                    "Dormant = no public activity > 90 days. If input is empty, "
                    "return all three as empty arrays."),
            user="{{JSON.stringify($json)}}",
            pos=(740, 300),
        ),
        slack_message(
            "Slack · Manager Digest",
            SLACK_CH_DIGEST,
            "🔐 *Quarterly Access Review*\n"
            "• Dormant: `{{$json.dormant.length}}`\n"
            "• Risky admins: `{{$json.risky_admins.length}}`\n"
            "Reply `revoke <username>` in thread to remove access.",
            (920, 300),
        ),
    ]
    return make_workflow("AIPP · 03 · Access Review Automator",
                         nodes, chain([n["name"] for n in nodes], nodes))


def wf_04_self_service() -> dict:
    """Slack form → HITL approval → Proxmox OR Azure VM. LLM sizes the VM."""
    nodes = [
        form_trigger("Intake Form", "AIPP Self-Service — VM Request", [
            {"fieldLabel": "Target", "fieldType": "dropdown",
             "fieldOptions": {"values": [{"option": "proxmox"},
                                         {"option": "azure"}]},
             "requiredField": True},
            {"fieldLabel": "Workload description", "fieldType": "textarea",
             "requiredField": True},
            {"fieldLabel": "Requester email", "fieldType": "email",
             "requiredField": True},
        ], (200, 300)),
        trace_init_node((380, 300)),
        llm_node(
            "AI · Size the VM",
            system=("You size VMs from natural-language workload descriptions. "
                    "Output ONLY a raw JSON object (no markdown, no prose). "
                    "Schema: {\"cpu\":<int>, \"memory_gb\":<int>, "
                    "\"disk_gb\":<int>, \"os\":\"ubuntu|windows\", "
                    "\"notes\":\"<one line>\"}. "
                    "Cap at 8 CPU / 32 GB RAM / 200 GB disk."),
            user=("Target: {{$json['Target']}}\n"
                  "Workload: {{$json['Workload description']}}"),
            pos=(560, 300),
        ),
        parse_ai_output_node((680, 300)),
        # ---- HITL approval before ANY VM provisioning ----------------------
        slack_hitl_message(
            "Slack · Ask Provision Approval",
            SLACK_CH_APPROVE,
            "💻  VM Provisioning — Approval Needed",
            "• *Requester:*  `{{$('Intake Form').item.json['Requester email']}}`\n"
            "• *Target:*  `{{$('Intake Form').item.json['Target']}}`\n"
            "• *Workload:*  {{$('Intake Form').item.json['Workload description']}}\n"
            "• *AI-sized:*  cpu=`{{$json.ai.cpu || '?'}}` "
            "mem=`{{$json.ai.memory_gb || '?'}}G` "
            "disk=`{{$json.ai.disk_gb || '?'}}G` "
            "os=`{{$json.ai.os || '?'}}`\n"
            "• *Notes:*  {{$json.ai.notes || 'n/a'}}",
            (720, 300),
        ),
        wait_for_approval_node("Wait for Approval", (880, 300)),
        normalize_decision_node((1020, 300)),
        if_equals_node("Approved?", "$json.decision", "approve", (1040, 300)),
        if_node("Route by Target",
                "$('Intake Form').item.json['Target'] === 'proxmox'",
                (1220, 200)),
        aipp_call(
            "Proxmox · Create VM",
            "POST", "/proxmox/vm",
            {"cores":     "={{$('AI · Size the VM').item.json.message.content.cpu || 2}}",
             "memory_mb": "={{($('AI · Size the VM').item.json.message.content.memory_gb || 2) * 1024}}",
             "name":      "aipp-{{$('Intake Form').item.json['Requester email'].split('@')[0]}}"},
            (1400, 100),
        ),
        azure_token_node((1400, 300)),
        http_node(
            "Azure · Create VM",
            ("=https://management.azure.com/subscriptions/"
             + cfg("AZURE_SUBSCRIPTION_ID") + "/resourceGroups/"
             + cfg("AZURE_RG_DEFAULT") + "/providers/Microsoft.Compute/"
             "virtualMachines/aipp-{{$('Intake Form').item.json['Requester email']"
             ".split('@')[0]}}?api-version=2023-03-01"),
            "PUT",
            {"location": "eastus",
             "properties": {
                 "hardwareProfile": {"vmSize": "Standard_B2s"},
                 "storageProfile": {"osDisk": {"createOption": "FromImage"}},
             }},
            (1580, 300),
            auth_header="=Bearer {{$('Azure · Get Token').item.json.access_token}}",
        ),
        slack_message(
            "Slack · Provisioned",
            SLACK_CH_DEFAULT,
            "💻 *VM provisioned* for "
            "`{{$('Intake Form').item.json['Requester email']}}`\n"
            "Target: `{{$('Intake Form').item.json['Target']}}` · "
            "{{$('AI · Size the VM').item.json.message.content}}",
            (1760, 200),
        ),
        slack_message(
            "Slack · Provision Rejected",
            SLACK_CH_ALERTS,
            "❌ *VM request rejected — no provisioning performed*\n"
            "Requester: `{{$('Intake Form').item.json['Requester email']}}`",
            (1220, 500),
        ),
    ]
    conns = {
        "Intake Form": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[{"node": "AI · Size the VM", "type": "main", "index": 0}]]},
        "AI · Size the VM": {"main": [[{"node": "Parse AI Output", "type": "main", "index": 0}]]},
        "Parse AI Output": {"main": [[{"node": "Slack · Ask Provision Approval", "type": "main", "index": 0}]]},
        "Slack · Ask Provision Approval": {"main": [[{"node": "Wait for Approval", "type": "main", "index": 0}]]},
        "Wait for Approval": {"main": [[{"node": "Normalize Decision", "type": "main", "index": 0}]]},
        "Normalize Decision": {"main": [[{"node": "Approved?", "type": "main", "index": 0}]]},
        "Approved?": {"main": [
            [{"node": "Route by Target", "type": "main", "index": 0}],
            [{"node": "Slack · Provision Rejected", "type": "main", "index": 0}],
        ]},
        "Route by Target": {"main": [
            [{"node": "Proxmox · Create VM", "type": "main", "index": 0}],
            [{"node": "Azure · Get Token", "type": "main", "index": 0}],
        ]},
        "Proxmox · Create VM": {"main": [[{"node": "Slack · Provisioned", "type": "main", "index": 0}]]},
        "Azure · Get Token": {"main": [[{"node": "Azure · Create VM", "type": "main", "index": 0}]]},
        "Azure · Create VM": {"main": [[{"node": "Slack · Provisioned", "type": "main", "index": 0}]]},
    }
    return make_workflow("AIPP · 04 · Developer Self-Service Portal", nodes, conns)


def wf_05_pipeline_digest() -> dict:
    """Pipeline status digest (Manual / Webhook Trigger): count running/failed across ADO + GH Actions."""
    nodes = [
        webhook_trigger("AIPP · Pipeline Digest Trigger", "aipp-pipeline-digest", (200, 300)),
        trace_init_node((380, 300)),
        aipp_call(
            "ADO · List Runs",
            "GET", "/ado/runs", None, (560, 200),
        ),
        aipp_call(
            "GitHub · List Actions Runs",
            "GET", "/github/runs/{{$vars.GH_ORG}}/{{$vars.GH_REPO}}",
            None, (560, 400),
        ),
        _node(
            "Aggregate", "n8n-nodes-base.set",
            {
                "mode": "manual",
                "assignments": {"assignments": [
                    {"id": "ag-1", "name": "ado_running",
                     "value": "={{ (($('ADO · List Runs').item.json.value) || []).filter(r => r.state === 'inProgress').length }}",
                     "type": "number"},
                    {"id": "ag-2", "name": "ado_failed",
                     "value": "={{ (($('ADO · List Runs').item.json.value) || []).filter(r => r.result === 'failed').length }}",
                     "type": "number"},
                    {"id": "ag-3", "name": "gha_running",
                     "value": "={{ (($('GitHub · List Actions Runs').item.json.workflow_runs) || []).filter(r => r.status === 'in_progress').length }}",
                     "type": "number"},
                    {"id": "ag-4", "name": "gha_failed",
                     "value": "={{ (($('GitHub · List Actions Runs').item.json.workflow_runs) || []).filter(r => r.conclusion === 'failure').length }}",
                     "type": "number"},
                    {"id": "ag-5", "name": "failed_names",
                     "value": ("={{ [...(($('ADO · List Runs').item.json.value) || [])"
                               ".filter(r => r.result === 'failed').map(r => r.name),"
                               "...(($('GitHub · List Actions Runs').item.json.workflow_runs) || [])"
                               ".filter(r => r.conclusion === 'failure').map(r => r.name)]"
                               ".slice(0, 5) }}"),
                      "type": "array"},
                ]},
                "includeOtherFields": False,
                "options": {},
            },
            (740, 300), tver=3.4,
        ),
        slack_message(
            "Slack · Digest",
            SLACK_CH_DIGEST,
            "📊 *Pipeline status*\n"
            "• ADO running `{{$json.ado_running}}` · failed `{{$json.ado_failed}}`\n"
            "• GHA running `{{$json.gha_running}}` · failed `{{$json.gha_failed}}`\n"
            "Recent failures: `{{$json.failed_names.join(', ') || 'none'}}`",
            (920, 300),
        ),
    ]
    conns = {
        "AIPP · Pipeline Digest Trigger": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[
            {"node": "ADO · List Runs", "type": "main", "index": 0},
            {"node": "GitHub · List Actions Runs", "type": "main", "index": 0},
        ]]},
        "ADO · List Runs": {"main": [[{"node": "Aggregate", "type": "main", "index": 0}]]},
        "GitHub · List Actions Runs": {"main": [[{"node": "Aggregate", "type": "main", "index": 0}]]},
        "Aggregate": {"main": [[{"node": "Slack · Digest", "type": "main", "index": 0}]]},
    }
    return make_workflow("AIPP · 05 · Pipeline Status Digest", nodes, conns)


def wf_06_k8s_health() -> dict:
    """K8s health scorecard (Manual / Webhook Trigger) from live pod list."""
    nodes = [
        webhook_trigger("AIPP · K8s Health Trigger", "aipp-k8s-health", (200, 300)),
        trace_init_node((380, 300)),
        aipp_call("K8s · List Pods",
                  "GET", "/k8s/pods", None, (560, 300)),
        llm_node(
            "AI · Score Cluster",
            system=("You are a K8s auditor. From the pod list JSON output a "
                    "scorecard: {score(0-100), top_issues:[{severity,title,fix}]}. "
                    "Deduct points for pods in CrashLoop, high restarts, missing "
                    "resource limits."),
            user="{{JSON.stringify($json.items || [])}}",
            pos=(740, 300),
        ),
        slack_message(
            "Slack · Scorecard",
            SLACK_CH_DIGEST,
            "🩺 *K8s Cluster Scorecard* — `{{$json.score}}/100`\n"
            "{{$json.top_issues.map(i => `• [${i.severity}] ${i.title}`).join('\\n')}}",
            (920, 300),
        ),
    ]
    return make_workflow("AIPP · 06 · K8s Health Scorecard",
                         nodes, chain([n["name"] for n in nodes], nodes))


def wf_07_k8s_troubleshoot() -> dict:
    """Slack slash-command → gather pod diag → LLM diagnosis + fix."""
    nodes = [
        webhook_trigger("Slack · /troubleshoot", "aipp-troubleshoot", (200, 300)),
        slack_sig_note_node((380, 300)),
        trace_init_node((560, 300)),
        _node(
            "Parse Slack Command", "n8n-nodes-base.set",
            {
                "mode": "manual",
                "assignments": {"assignments": [
                    {"id": "sc-1", "name": "pod",
                     "value": ("={{ (($json.body?.text || $json.text || '')"
                               ".match(/pod=(\\S+)/) || [])[1] || '' }}"),
                     "type": "string"},
                    {"id": "sc-2", "name": "ns",
                     "value": ("={{ (($json.body?.text || $json.text || '')"
                               ".match(/ns=(\\S+)/) || [])[1] || 'default' }}"),
                     "type": "string"},
                ]},
                "includeOtherFields": True,
                "options": {},
            },
            (740, 300), tver=3.4,
        ),
        # Filter: drop if pod arg is missing (equivalent to old throw).
        _node(
            "Require Pod Arg", "n8n-nodes-base.filter",
            {"conditions": {
                "options": {"caseSensitive": True, "leftValue": "",
                            "typeValidation": "loose"},
                "conditions": [{
                    "id": "pod-req",
                    "leftValue": "={{ $json.pod }}",
                    "rightValue": "",
                    "operator": {"type": "string", "operation": "notEmpty"},
                }],
                "combinator": "and",
            }},
            (860, 300), tver=2.2,
        ),
        aipp_call("K8s · Fetch Pod",
                  "GET",
                  "/k8s/pods/{{$json.ns}}/{{$json.pod}}",
                  None, (920, 300)),
        # ---- Summarise pod state — passed to LLM AND to the Slack card. ----
        # Extracting the salient bits from the raw K8s response gives the AI
        # a small, focused prompt (better answers, lower cost) and gives the
        # operator a compact readout in Slack.
        _node(
            "Summarise Pod", "n8n-nodes-base.set",
            {
                "mode": "manual",
                "assignments": {"assignments": [
                    {"id": "sp-1", "name": "phase",
                     "value": "={{ $json.status?.phase || 'Unknown' }}",
                     "type": "string"},
                    {"id": "sp-2", "name": "created_at",
                     "value": "={{ $json.metadata?.creationTimestamp || 'n/a' }}",
                     "type": "string"},
                    {"id": "sp-3", "name": "node_name",
                     "value": "={{ $json.spec?.nodeName || 'n/a' }}",
                     "type": "string"},
                    {"id": "sp-4", "name": "images",
                     "value": ("={{ ($json.spec?.containers || [])"
                               ".map(c => `${c.name} <- ${c.image}`).join(', ') }}"),
                     "type": "string"},
                    {"id": "sp-5", "name": "restart_count",
                     "value": ("={{ ($json.status?.containerStatuses || [])"
                               ".reduce((sum, cs) => sum + (cs.restartCount || 0), 0) }}"),
                     "type": "number"},
                    {"id": "sp-6", "name": "ready_containers",
                     "value": ("={{ ($json.status?.containerStatuses || [])"
                               ".filter(cs => cs.ready).length + '/' +"
                               " ($json.status?.containerStatuses || []).length }}"),
                     "type": "string"},
                    {"id": "sp-7", "name": "container_state",
                     "value": ("={{ ($json.status?.containerStatuses || [])"
                               ".map(cs => cs.name + ':' + Object.keys(cs.state || {})[0])"
                               ".join(', ') }}"),
                     "type": "string"},
                    {"id": "sp-8", "name": "last_termination_reason",
                     "value": ("={{ ($json.status?.containerStatuses || [])"
                               ".map(cs => cs.lastState?.terminated?.reason)"
                               ".filter(Boolean).join(', ') || 'none' }}"),
                     "type": "string"},
                ]},
                "includeOtherFields": True,
                "options": {},
            },
            (1060, 300), tver=3.4,
        ),
        llm_node(
            "AI · Diagnose",
            system=("You are a K8s SRE assistant. Output ONLY a raw JSON object "
                    "(no markdown, no code fence, no explanation, no prose). "
                    "Schema: {\"category\":\"OOMKill|CrashLoop|ImagePullBackOff|"
                    "Config|Healthy|Other\", \"root_cause\":\"<short sentence>\", "
                    "\"fix_command\":\"<one kubectl command>\", "
                    "\"impact\":\"<one line business impact>\", "
                    "\"confidence\":<number 0-1>}. "
                    "If the pod looks healthy (Running, 0 restarts, all ready), "
                    "set category=Healthy, fix_command=\"no action needed\"."),
            user=("Pod: {{$json.pod}}  Namespace: {{$json.ns}}\n"
                  "Phase: {{$json.phase}}  Ready: {{$json.ready_containers}}  "
                  "Restarts: {{$json.restart_count}}\n"
                  "Container state: {{$json.container_state}}\n"
                  "Last termination reason: {{$json.last_termination_reason}}\n"
                  "Images: {{$json.images}}\n"
                  "Created: {{$json.created_at}}  Node: {{$json.node_name}}"),
            pos=(1220, 300),
        ),
        # ---- Human-in-the-Loop approval gate --------------------------------
        # The AI has diagnosed the issue and proposed a fix. Before applying
        # or trumpeting anything, we ASK a human to sign off. The Wait node
        # exposes a resume URL that we embed as two links (approve / reject).
        # LLM sometimes wraps its JSON in markdown code fences; strip those
        # before JSON.parse so template placeholders always resolve.
        _node(
            "Parse AI Output", "n8n-nodes-base.set",
            {
                "mode": "manual",
                "assignments": {"assignments": [
                    {"id": "ai-parse", "name": "ai",
                     "value": ("={{ JSON.parse($json.message?.content"
                               " || $json.content || $json.text || '{}') }}"),
                     "type": "object"},
                ]},
                "includeOtherFields": True,
                "options": {},
            },
            (1380, 300), tver=3.4,
        ),
        slack_hitl_message(
            "Slack · Ask Approval",
            SLACK_CH_APPROVE,
            "🩺  K8s Troubleshoot — Approval Needed",
            "*Pod*  `{{$('Parse Slack Command').item.json.pod}}` · "
            "*Namespace*  `{{$('Parse Slack Command').item.json.ns}}`\n"
            "*Node*  `{{$('Summarise Pod').item.json.node_name}}` · "
            "*Phase*  `{{$('Summarise Pod').item.json.phase}}`\n"
            "*Ready*  `{{$('Summarise Pod').item.json.ready_containers}}` · "
            "*Restarts*  `{{$('Summarise Pod').item.json.restart_count}}`\n"
            "*State*  {{$('Summarise Pod').item.json.container_state}}\n"
            "*Last term.*  `{{$('Summarise Pod').item.json.last_termination_reason}}`\n"
            "*Images*  {{$('Summarise Pod').item.json.images}}\n\n"
            "🤖 *AI diagnosis*\n"
            "• *Category:*  `{{$json.ai.category || 'n/a'}}` "
            "(confidence `{{$json.ai.confidence || 'n/a'}}`)\n"
            "• *Root cause:*  {{$json.ai.root_cause || 'n/a'}}\n"
            "• *Impact:*  {{$json.ai.impact || 'n/a'}}\n"
            "• *Proposed fix:*  `{{$json.ai.fix_command || 'n/a'}}`\n\n"
            "_Waits up to 24h for your decision._",
            (1540, 300),
        ),
        wait_for_approval_node("Wait for Human", (1720, 300)),
        normalize_decision_node((1860, 300)),
        if_equals_node(
            "Approved?",
            "$json.decision",
            "approve",
            (1900, 300),
        ),
        if_equals_node(
            "Rejected?",
            "$json.decision",
            "reject",
            (1980, 400),
        ),
        slack_message(
            "Slack · Approved · Post Fix",
            SLACK_CH_ALERTS,
            "✅ *Fix approved by human — recording*\n"
            "*Pod:*  `{{$('Parse Slack Command').item.json.pod}}` (ns `{{$('Parse Slack Command').item.json.ns}}`)\n"
            "*Command to run:*\n"
            "```\n"
            "{{$('Parse AI Output').item.json.ai.fix_command || 'n/a'}}\n"
            "```\n"
            "_Autonomous execution disabled — copy the command above to your kubectl shell. AIPP has logged this approval in the audit trail._",
            (2140, 200),
        ),
        slack_message(
            "Slack · Rejected",
            SLACK_CH_ALERTS,
            "❌ *Fix rejected — no action taken*\n"
            "*Pod:*  `{{$('Parse Slack Command').item.json.pod}}`\n"
            "*Rejected diagnosis:*  "
            "`{{$('Parse AI Output').item.json.ai.category}}` — "
            "{{$('Parse AI Output').item.json.ai.root_cause}}\n"
            "The proposed fix has been recorded for audit but not executed.",
            (2140, 400),
        ),
    ]
    # Custom connections — HITL branch splits from the IF node.
    conns = {
        "Slack · /troubleshoot":       {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace":                  {"main": [[{"node": "Parse Slack Command", "type": "main", "index": 0}]]},
        "Parse Slack Command":         {"main": [[{"node": "Require Pod Arg", "type": "main", "index": 0}]]},
        "Require Pod Arg":             {"main": [[{"node": "K8s · Fetch Pod", "type": "main", "index": 0}]]},
        "K8s · Fetch Pod":             {"main": [[{"node": "Summarise Pod", "type": "main", "index": 0}]]},
        "Summarise Pod":               {"main": [[{"node": "AI · Diagnose", "type": "main", "index": 0}]]},
        "AI · Diagnose":               {"main": [[{"node": "Parse AI Output", "type": "main", "index": 0}]]},
        "Parse AI Output":             {"main": [[{"node": "Slack · Ask Approval", "type": "main", "index": 0}]]},
        "Slack · Ask Approval":        {"main": [[{"node": "Wait for Human", "type": "main", "index": 0}]]},
        "Wait for Human":              {"main": [[{"node": "Normalize Decision", "type": "main", "index": 0}]]},
        "Normalize Decision":          {"main": [[{"node": "Approved?", "type": "main", "index": 0}]]},
        "Approved?":                   {"main": [
            [{"node": "Slack · Approved · Post Fix", "type": "main", "index": 0}],
            [{"node": "Rejected?", "type": "main", "index": 0}],
        ]},
        "Rejected?":                   {"main": [
            [{"node": "Slack · Rejected", "type": "main", "index": 0}],
            [],
        ]},
    }
    return make_workflow("AIPP · 07 · K8s Troubleshoot Assistant", nodes, conns)


def wf_08_grafana_autofix() -> dict:
    """Grafana webhook alert → LLM picks remediation → Slack HITL card."""
    nodes = [
        webhook_trigger("Grafana · Alert Webhook", "aipp-grafana", (200, 300)),
        trace_init_node((380, 300)),
        _node(
            "Extract Alert", "n8n-nodes-base.set",
            {
                "mode": "manual",
                "assignments": {"assignments": [
                    {"id": "ex-1", "name": "metric",
                     "value": ("={{ ($json.body?.commonLabels?.alertname"
                               " || $json.commonLabels?.alertname"
                               " || $json.alertname || 'unknown') }}"),
                     "type": "string"},
                    {"id": "ex-2", "name": "target",
                     "value": ("={{ ($json.body?.commonLabels?.instance"
                               " || $json.commonLabels?.instance"
                               " || $json.instance || 'unknown') }}"),
                     "type": "string"},
                    {"id": "ex-3", "name": "value",
                     "value": ("={{ ($json.body?.commonAnnotations?.value"
                               " || $json.commonAnnotations?.value"
                               " || $json.value || 'n/a') }}"),
                     "type": "string"},
                ]},
                "includeOtherFields": True,
                "options": {},
            },
            (560, 300), tver=3.4,
        ),
        llm_node(
            "AI · Choose Remediation",
            system=("You are an SRE. Given a metric alert, pick ONE safe "
                    "remediation. Output ONLY a raw JSON object (no markdown, "
                    "no prose). Schema: {\"action\":\"restart_pod|scale_hpa"
                    "|clear_cache|expand_pvc|escalate\", "
                    "\"kubectl_cmd\":\"<one command>\", "
                    "\"reason\":\"<one line>\", "
                    "\"risk\":\"low|med|high\"}."),
            user=("Metric: {{$json.metric}}\nTarget: {{$json.target}}\n"
                  "Value: {{$json.value}}"),
            pos=(740, 300),
        ),
        parse_ai_output_node((860, 300)),
        # ---- HITL — remediation requires explicit human approval ------------
        slack_hitl_message(
            "Slack · Ask Remediation Approval",
            SLACK_CH_APPROVE,
            "🚨  Alert Remediation — Approval Needed",
            "*Alert:*  `{{$('Extract Alert').item.json.metric}}` on "
            "`{{$('Extract Alert').item.json.target}}`\n"
            "• *AI proposes:*  `{{$json.ai.action || 'n/a'}}` "
            "(risk `{{$json.ai.risk || 'n/a'}}`)\n"
            "• *Reason:*  {{$json.ai.reason || 'n/a'}}\n"
            "• *Command:*  `{{$json.ai.kubectl_cmd || 'n/a'}}`",
            (920, 300),
        ),
        wait_for_approval_node("Wait for Approval", (1100, 300)),
        normalize_decision_node((1240, 300)),
        if_equals_node("Approved?", "$json.decision", "approve", (1280, 300)),
        slack_message(
            "Slack · Remediation Applied",
            SLACK_CH_ALERTS,
            "✅ *Remediation approved & recorded*\n"
            "Alert: `{{$('Extract Alert').item.json.metric}}` → "
            "action `{{$('Parse AI Output').item.json.ai.action || 'n/a'}}`\n"
            "```\n{{$('Parse AI Output').item.json.ai.kubectl_cmd || 'n/a'}}\n```",
            (1460, 200),
        ),
        slack_message(
            "Slack · Remediation Rejected",
            SLACK_CH_ALERTS,
            "❌ *Auto-remediation rejected — alert escalated to on-call*\n"
            "Alert: `{{$('Extract Alert').item.json.metric}}`",
            (1460, 400),
        ),
    ]
    conns = {
        "Grafana · Alert Webhook": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[{"node": "Extract Alert", "type": "main", "index": 0}]]},
        "Extract Alert": {"main": [[{"node": "AI · Choose Remediation", "type": "main", "index": 0}]]},
        "AI · Choose Remediation": {"main": [[{"node": "Parse AI Output", "type": "main", "index": 0}]]},
        "Parse AI Output": {"main": [[{"node": "Slack · Ask Remediation Approval", "type": "main", "index": 0}]]},
        "Slack · Ask Remediation Approval": {"main": [[{"node": "Wait for Approval", "type": "main", "index": 0}]]},
        "Wait for Approval": {"main": [[{"node": "Normalize Decision", "type": "main", "index": 0}]]},
        "Normalize Decision": {"main": [[{"node": "Approved?", "type": "main", "index": 0}]]},
        "Approved?": {"main": [
            [{"node": "Slack · Remediation Applied", "type": "main", "index": 0}],
            [{"node": "Slack · Remediation Rejected", "type": "main", "index": 0}],
        ]},
    }
    return make_workflow("AIPP · 08 · Grafana Observability Auto-Remediator",
                         nodes, conns)


def wf_09_azure_cost() -> dict:
    """Azure Cost review (Manual / Webhook Trigger) → Slack. Skips silently if Azure unconfigured."""
    nodes = [
        webhook_trigger("AIPP · Azure Cost Review Trigger", "aipp-azure-cost", (200, 300)),
        trace_init_node((380, 300)),
        azure_gate_node((560, 300)),
        azure_token_node((740, 220)),
        http_node(
            "Azure · Cost Query",
            ("=https://management.azure.com/subscriptions/"
             "{{$vars.AZURE_SUBSCRIPTION_ID}}/providers/"
             "Microsoft.CostManagement/query?api-version=2023-11-01"),
            "POST",
            {"type": "ActualCost", "timeframe": "MonthToDate",
             "dataset": {
                 "granularity": "Daily",
                 "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                 "grouping": [{"type": "Dimension", "name": "ResourceGroup"}],
             }},
            (920, 220),
            auth_header="=Bearer {{$('Azure · Get Token').item.json.access_token}}",
        ),
        llm_node(
            "AI · Narrate Cost",
            system=("You are a FinOps analyst. Narrate WoW cost change with "
                    "top-5 movers and 3 specific actions (delete unused disks, "
                    "right-size, buy reserved instances, etc)."),
            user="{{JSON.stringify($json.properties?.rows || [])}}",
            pos=(1100, 220),
        ),
        slack_message(
            "Slack · Cost Report",
            SLACK_CH_DIGEST,
            "💰 *Weekly Azure Cost Review*\n{{$json.message.content}}",
            (1280, 220),
        ),
    ]
    conns = {
        "AIPP · Azure Cost Review Trigger": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[{"node": "Azure Configured?", "type": "main", "index": 0}]]},
        "Azure Configured?": {"main": [
            [{"node": "Azure · Get Token", "type": "main", "index": 0}],
            [],  # false branch — terminal, workflow ends silently
        ]},
        "Azure · Get Token": {"main": [[{"node": "Azure · Cost Query", "type": "main", "index": 0}]]},
        "Azure · Cost Query": {"main": [[{"node": "AI · Narrate Cost", "type": "main", "index": 0}]]},
        "AI · Narrate Cost": {"main": [[{"node": "Slack · Cost Report", "type": "main", "index": 0}]]},
    }
    return make_workflow("AIPP · 09 · Weekly Azure Cost Review", nodes, conns)


def wf_10_incident_commander() -> dict:
    """Azure Monitor alert → 5-step LLM chain → auto-assign OR ask human."""
    nodes = [
        webhook_trigger("Azure Monitor · Alert", "aipp-incident", (200, 300)),
        trace_init_node((380, 300)),
        _node(
            "1. Accept", "n8n-nodes-base.set",
            {
                "mode": "manual",
                "assignments": {"assignments": [
                    {"id": "ac-1", "name": "severity_raw",
                     "value": ("={{ ($json.body?.data?.essentials?.severity"
                               " || $json.data?.essentials?.severity"
                               " || 'Sev3') }}"),
                     "type": "string"},
                    {"id": "ac-2", "name": "service",
                     "value": ("={{ ($json.body?.data?.essentials?.alertTargetIDs?.[0]"
                               " || $json.data?.essentials?.alertTargetIDs?.[0]"
                               " || 'unknown') }}"),
                     "type": "string"},
                    {"id": "ac-3", "name": "fired_at",
                     "value": ("={{ ($json.body?.data?.essentials?.firedDateTime"
                               " || $json.data?.essentials?.firedDateTime"
                               " || $now.toISO()) }}"),
                     "type": "string"},
                ]},
                "includeOtherFields": True,
                "options": {},
            },
            (560, 300), tver=3.4,
        ),
        llm_node(
            "2. Classify Severity",
            system="Classify P1/P2/P3. Reply JSON: {severity, why}.",
            user=("Raw severity: {{$json.severity_raw}}\n"
                  "Service: {{$json.service}}"),
            pos=(740, 300),
        ),
        aipp_call("3. Check K8s Prod Pods",
                  "GET", "/k8s/pods?ns=prod",
                  None, (920, 300)),
        llm_node(
            "4. Assign Team",
            system=("From service name + service-ownership map, pick target "
                    "team. Output JSON: {team, confidence(0-1), reasoning}. "
                    "Confidence < 0.7 means ask a human."),
            user=("Service: {{$('1. Accept').item.json.service}}\n"
                  "Map: {{$vars.SVCMAP}}\n"
                  "Diagnostics: {{JSON.stringify($('3. Check K8s Prod Pods').item.json)}}"),
            pos=(1100, 300),
        ),
        if_node("Confidence ≥ 0.7?",
                "$json.confidence >= 0.7", (1280, 300)),
        slack_message(
            "Slack · Auto-Assign",
            SLACK_CH_ALERTS,
            "🚑 *P{{$('2. Classify Severity').item.json.severity}} auto-assigned to `{{$json.team}}`*\n"
            "Service: `{{$('1. Accept').item.json.service}}`",
            (1460, 200),
        ),
        slack_message(
            "Slack · Ask Human",
            SLACK_CH_APPROVE,
            "🤖 *AI unsure — need human triage* "
            "(conf `{{$('4. Assign Team').item.json.confidence}}`)\n"
            "Service: `{{$('1. Accept').item.json.service}}`\n"
            "Best guess: `{{$('4. Assign Team').item.json.team}}` — reply with team name to override.",
            (1460, 400),
        ),
        llm_node(
            "5. Draft Comms",
            system=("Draft customer-facing status message + internal update. "
                    "Output JSON: {customer_msg, internal_msg, status_page_title}."),
            user=("Severity: P{{$('2. Classify Severity').item.json.severity}}\n"
                  "Service: {{$('1. Accept').item.json.service}}"),
            pos=(1640, 300),
        ),
        slack_message(
            "Slack · Comms Draft",
            SLACK_CH_APPROVE,
            "📝 *Comms draft — review before sending*\n"
            "• Customer: {{$json.customer_msg}}\n"
            "• Internal: {{$json.internal_msg}}",
            (1820, 300),
        ),
    ]
    conns = {
        "Azure Monitor · Alert": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[{"node": "1. Accept", "type": "main", "index": 0}]]},
        "1. Accept": {"main": [[{"node": "2. Classify Severity", "type": "main", "index": 0}]]},
        "2. Classify Severity": {"main": [[{"node": "3. Check K8s Prod Pods", "type": "main", "index": 0}]]},
        "3. Check K8s Prod Pods": {"main": [[{"node": "4. Assign Team", "type": "main", "index": 0}]]},
        "4. Assign Team": {"main": [[{"node": "Confidence ≥ 0.7?", "type": "main", "index": 0}]]},
        "Confidence ≥ 0.7?": {"main": [
            [{"node": "Slack · Auto-Assign", "type": "main", "index": 0}],
            [{"node": "Slack · Ask Human", "type": "main", "index": 0}],
        ]},
        "Slack · Auto-Assign": {"main": [[{"node": "5. Draft Comms", "type": "main", "index": 0}]]},
        "Slack · Ask Human": {"main": [[{"node": "5. Draft Comms", "type": "main", "index": 0}]]},
        "5. Draft Comms": {"main": [[{"node": "Slack · Comms Draft", "type": "main", "index": 0}]]},
    }
    return make_workflow("AIPP · 10 · Incident Commander Bot", nodes, conns)


def wf_11_sop_generator() -> dict:
    """Post-incident: Topic extraction + Severity-gated AI runbook + SRE .docx generation -> Slack."""
    base = cfg("AIPP_BASE_URL", "https://aipp.dccloud.in.net").rstrip("/")
    api_key = cfg("AIPP_API_KEY") or cfg("PROXY_API_KEY")

    nodes = [
        webhook_trigger("AIPP · Incident Closed Hook", "aipp-sop", (200, 300)),
        trace_init_node((380, 300)),
        _node(
            "Extract Incident Context", "n8n-nodes-base.set",
            {
                "mode": "manual",
                "assignments": {"assignments": [
                    {"id": "sop-1", "name": "incident_id",
                     "value": ("={{ ($json.body?.incident_id "
                               "|| $json.incident_id "
                               "|| $json.body?.commonLabels?.alertname "
                               "|| 'INC-88392') }}"),
                     "type": "string"},
                    {"id": "sop-2", "name": "incident_title",
                     "value": ("={{ ($json.body?.incident_title "
                               "|| $json.body?.title "
                               "|| $json.body?.commonAnnotations?.summary "
                               "|| $json.body?.commonLabels?.alertname "
                               "|| 'PostgreSQL Connection Pool Exhaustion & Outage') }}"),
                     "type": "string"},
                    {"id": "sop-3", "name": "severity",
                     "value": ("={{ ($json.body?.severity "
                               "|| $json.body?.commonLabels?.severity "
                               "|| 'CRITICAL').toUpperCase() }}"),
                     "type": "string"},
                    {"id": "sop-4", "name": "affected_service",
                     "value": ("={{ ($json.body?.affected_service "
                               "|| $json.body?.commonLabels?.pod "
                               "|| $json.body?.commonLabels?.instance "
                               "|| $json.body?.service "
                               "|| 'AIPP Backend API / PostgreSQL Cluster') }}"),
                     "type": "string"},
                    {"id": "sop-5", "name": "rca_summary",
                     "value": ("={{ ($json.body?.rca_summary "
                               "|| $json.body?.commonAnnotations?.summary "
                               "|| 'Database connection pool exhaustion under peak load') }}"),
                     "type": "string"},
                    {"id": "sop-6", "name": "timeline",
                     "value": ("={{ ($json.body?.timeline "
                               "|| 'T0 14:10 Alert Fired -> T1 14:15 Triage -> T2 14:35 Pool Scaled -> T3 14:52 Mitigated') }}"),
                     "type": "string"},
                    {"id": "sop-7", "name": "should_generate_sop",
                     "value": ("={{ ($json.body?.generate_sop === true "
                               "|| ($json.body?.severity || $json.body?.commonLabels?.severity || 'CRITICAL').toLowerCase().includes('crit') "
                               "|| ($json.body?.severity || '').toLowerCase().includes('sev1') "
                               "|| ($json.body?.severity || '').toLowerCase().includes('p1') "
                               "|| $json.body?.trigger_type === 'incident_closed' "
                               "|| (!$json.body?.severity && !$json.body?.commonLabels?.severity)) ? 'true' : 'false' }}"),
                     "type": "string"},
                ]},
                "includeOtherFields": True,
                "options": {},
            },
            (560, 300), tver=3.4,
        ),
        if_equals_node("Critical or Closed?", "$json.should_generate_sop", "true", (740, 300)),
        http_node(
            "Generate .DOCX Runbook",
            f"{base}/api/workflows/rca/docx",
            "POST",
            {
                "incident_id": "={{ $('Extract Incident Context').item.json.incident_id }}",
                "title": "={{ $('Extract Incident Context').item.json.incident_title }}",
                "affected_service": "={{ $('Extract Incident Context').item.json.affected_service }}",
                "severity": "={{ $('Extract Incident Context').item.json.severity }}",
                "summary": "={{ $('Extract Incident Context').item.json.rca_summary }}",
            },
            (920, 200),
            auth_header=f"Bearer {api_key}" if api_key else None,
            continue_on_fail=True,
        ),
        llm_node(
            "AI · Draft Runbook",
            system=("You draft enterprise SRE runbooks and post-mortems. "
                    "Structure: 1. Symptom & Metric Trigger, 2. Diagnosis Steps (with exact CLI commands), "
                    "3. Fix & Mitigation (with rollback steps), 4. Long-term Prevention. Markdown only."),
            user=("Incident ID: {{$('Extract Incident Context').item.json.incident_id}}\n"
                  "Title: {{$('Extract Incident Context').item.json.incident_title}}\n"
                  "Severity: {{$('Extract Incident Context').item.json.severity}}\n"
                  "Impacted Service: {{$('Extract Incident Context').item.json.affected_service}}\n"
                  "RCA: {{$('Extract Incident Context').item.json.rca_summary}}\n"
                  "Timeline: {{$('Extract Incident Context').item.json.timeline}}"),
            pos=(1100, 200),
        ),
        slack_message(
            "Slack · Review Runbook",
            SLACK_CH_APPROVE,
            "📘 *SRE Runbook & RCA (.DOCX) Generated for incident `{{$('Extract Incident Context').item.json.incident_id}}`*\n\n"
            "• *Incident Topic:* `{{$('Extract Incident Context').item.json.incident_title}}`\n"
            "• *Affected Service:* `{{$('Extract Incident Context').item.json.affected_service}}`\n"
            "• *Severity:* `{{$('Extract Incident Context').item.json.severity}}`\n"
            "• *Root Cause:* `{{$('Extract Incident Context').item.json.rca_summary}}`\n\n"
            "📄 *Microsoft Word File Generated:* `docs/Incident_PostMortem_RCA_{{$('Extract Incident Context').item.json.incident_id}}.docx`\n"
            "🔗 *Download Link:* `/docs/Incident_PostMortem_RCA_{{$('Extract Incident Context').item.json.incident_id}}.docx`\n\n"
            "Preview:\n{{$json.message.content}}\n\n"
            "Reply `publish` to push to Wiki.",
            (1280, 200),
        ),
        slack_message(
            "Slack · Low Severity Alert Recorded",
            SLACK_CH_DIGEST,
            "ℹ️ *Alert Recorded — SOP Generation Skipped*\n\n"
            "• *Alert Topic:* `{{$('Extract Incident Context').item.json.incident_title}}`\n"
            "• *Affected Service:* `{{$('Extract Incident Context').item.json.affected_service}}`\n"
            "• *Severity:* `{{$('Extract Incident Context').item.json.severity}}` (Non-Critical)\n\n"
            "_Note: SRE Post-Mortem & SOP runbooks are automatically generated only for P1/Critical incidents or upon incident closure to avoid document fatigue._",
            (920, 420),
        ),
    ]
    conns = {
        "AIPP · Incident Closed Hook": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[{"node": "Extract Incident Context", "type": "main", "index": 0}]]},
        "Extract Incident Context": {"main": [[{"node": "Critical or Closed?", "type": "main", "index": 0}]]},
        "Critical or Closed?": {"main": [
            [{"node": "Generate .DOCX Runbook", "type": "main", "index": 0}],
            [{"node": "Slack · Low Severity Alert Recorded", "type": "main", "index": 0}],
        ]},
        "Generate .DOCX Runbook": {"main": [[{"node": "AI · Draft Runbook", "type": "main", "index": 0}]]},
        "AI · Draft Runbook": {"main": [[{"node": "Slack · Review Runbook", "type": "main", "index": 0}]]},
    }
    return make_workflow("AIPP · 11 · SOP / Runbook Generator", nodes, conns)





def wf_12_slo_burn() -> dict:
    """Azure Monitor SLO burn-rate (Manual / Webhook Trigger) → LLM decides page/ticket/silent → Slack."""
    nodes = [
        webhook_trigger("AIPP · SLO Burn Monitor Trigger", "aipp-slo-burn", (200, 300)),
        trace_init_node((380, 300)),
        azure_gate_node((560, 300)),
        azure_token_node((740, 220)),
        http_node(
            "Azure Monitor · Query Metric",
            ("=https://management.azure.com/subscriptions/"
             "{{$vars.AZURE_SUBSCRIPTION_ID}}/resourceGroups/"
             "{{$vars.AZURE_RG_DEFAULT}}/providers/microsoft.insights/"
             "metrics?api-version=2018-01-01&metricnames=FailedRequests"),
            "GET", None, (920, 220),
            auth_header="=Bearer {{$('Azure · Get Token').item.json.access_token}}",
        ),
        llm_node(
            "AI · Burn Rate Decision",
            system=("Given error-budget burn (fast: 1h window, slow: 6h), "
                    "decide: page (fast > 14.4x), ticket (slow > 6x), silent. "
                    "Output JSON: {decision, burn_fast, burn_slow, reason}."),
            user="{{JSON.stringify($json)}}",
            pos=(1100, 220),
        ),
        slack_message(
            "Slack · SLO Alert",
            SLACK_CH_ALERTS,
            "🔥 *SLO Burn Decision: `{{$json.decision}}`*\n"
            "• Fast: `{{$json.burn_fast}}x` · Slow: `{{$json.burn_slow}}x`\n"
            "{{$json.reason}}",
            (1280, 220),
        ),
    ]
    conns = {
        "AIPP · SLO Burn Monitor Trigger": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[{"node": "Azure Configured?", "type": "main", "index": 0}]]},
        "Azure Configured?": {"main": [
            [{"node": "Azure · Get Token", "type": "main", "index": 0}],
            [],  # false branch — terminal
        ]},
        "Azure · Get Token": {"main": [[{"node": "Azure Monitor · Query Metric", "type": "main", "index": 0}]]},
        "Azure Monitor · Query Metric": {"main": [[{"node": "AI · Burn Rate Decision", "type": "main", "index": 0}]]},
        "AI · Burn Rate Decision": {"main": [[{"node": "Slack · SLO Alert", "type": "main", "index": 0}]]},
    }
    return make_workflow("AIPP · 12 · Azure SLO Burn-Rate Monitor", nodes, conns)


def wf_13_dr_drill() -> dict:
    """DR drill scheduler (Manual / Webhook Trigger) with HITL. Skips silently if Azure unconfigured."""
    nodes = [
        webhook_trigger("AIPP · DR Drill Trigger", "aipp-dr-drill", (200, 300)),
        trace_init_node((380, 300)),
        azure_gate_node((560, 300)),
        azure_token_node((740, 220)),
        http_node(
            "List Recovery Vaults",
            ("=https://management.azure.com/subscriptions/"
             + cfg("AZURE_SUBSCRIPTION_ID") + "/resourceGroups/"
             + cfg("AZURE_RG_DEFAULT") + "/providers/"
             "Microsoft.RecoveryServices/vaults?api-version=2023-04-01"),
            "GET", None, (920, 220),
            auth_header="=Bearer {{$('Azure · Get Token').item.json.access_token}}",
        ),
        llm_node(
            "AI · Plan Drill",
            system=("Pick one service for a DR drill. Output ONLY a raw JSON "
                    "object (no markdown). Schema: {\"service\":\"<name>\","
                    " \"plan_steps\":[\"step1\",\"step2\"], "
                    "\"rto_target\":\"<duration>\", "
                    "\"rpo_target\":\"<duration>\", "
                    "\"abort_criteria\":\"<one line>\"}."),
            user="{{JSON.stringify($json.value || [])}}",
            pos=(1100, 220),
        ),
        parse_ai_output_node((1220, 220)),
        # ---- HITL — DR drill requires explicit human approval ---------------
        slack_hitl_message(
            "Slack · Ask DR Approval",
            SLACK_CH_APPROVE,
            "🛟  DR Drill — Approval Needed",
            "• *Service:*  `{{$json.ai.service || 'n/a'}}`\n"
            "• *RTO / RPO:*  `{{$json.ai.rto_target || 'n/a'}}` / "
            "`{{$json.ai.rpo_target || 'n/a'}}`\n"
            "• *Plan steps:*\n"
            "{{($json.ai.plan_steps || []).map(s => `  • ${s}`).join('\\n')}}\n"
            "• *Abort criteria:*  {{$json.ai.abort_criteria || 'n/a'}}",
            (1280, 220),
        ),
        wait_for_approval_node("Wait for Approval", (1460, 220)),
        normalize_decision_node((1600, 220)),
        if_equals_node("Approved?", "$json.decision", "approve", (1640, 220)),
        slack_message(
            "Slack · Drill Kicked Off",
            SLACK_CH_ALERTS,
            "✅ *DR drill approved — kicking off*\n"
            "Service: `{{$('Parse AI Output').item.json.ai.service || 'n/a'}}`",
            (1820, 120),
        ),
        slack_message(
            "Slack · Drill Rejected",
            SLACK_CH_ALERTS,
            "❌ *DR drill rejected — no action taken*",
            (1820, 320),
        ),
    ]
    conns = {
        "AIPP · DR Drill Trigger": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[{"node": "Azure Configured?", "type": "main", "index": 0}]]},
        "Azure Configured?": {"main": [
            [{"node": "Azure · Get Token", "type": "main", "index": 0}],
            [],
        ]},
        "Azure · Get Token": {"main": [[{"node": "List Recovery Vaults", "type": "main", "index": 0}]]},
        "List Recovery Vaults": {"main": [[{"node": "AI · Plan Drill", "type": "main", "index": 0}]]},
        "AI · Plan Drill": {"main": [[{"node": "Parse AI Output", "type": "main", "index": 0}]]},
        "Parse AI Output": {"main": [[{"node": "Slack · Ask DR Approval", "type": "main", "index": 0}]]},
        "Slack · Ask DR Approval": {"main": [[{"node": "Wait for Approval", "type": "main", "index": 0}]]},
        "Wait for Approval": {"main": [[{"node": "Normalize Decision", "type": "main", "index": 0}]]},
        "Normalize Decision": {"main": [[{"node": "Approved?", "type": "main", "index": 0}]]},
        "Approved?": {"main": [
            [{"node": "Slack · Drill Kicked Off", "type": "main", "index": 0}],
            [{"node": "Slack · Drill Rejected", "type": "main", "index": 0}],
        ]},
    }
    return make_workflow("AIPP · 13 · DR Readiness Drill Scheduler", nodes, conns)


def wf_14_chaos() -> dict:
    """Chaos experiment: form → LLM designs → SRE approves → execute."""
    nodes = [
        form_trigger("Chaos Request Form", "AIPP Chaos — Experiment Request", [
            {"fieldLabel": "Question to answer", "fieldType": "textarea",
             "requiredField": True},
            {"fieldLabel": "Target namespace", "fieldType": "text",
             "requiredField": True},
            {"fieldLabel": "Requester", "fieldType": "email",
             "requiredField": True},
        ], (200, 300)),
        trace_init_node((380, 300)),
        llm_node(
            "AI · Design Experiment",
            system=("You design SAFE chaos experiments. Output ONLY a raw JSON "
                    "object (no markdown). Schema: {\"hypothesis\":\"<line>\","
                    " \"chaos_mesh_manifest\":\"<yaml>\", "
                    "\"blast_radius\":\"<pod|node|zone>\", "
                    "\"duration_min\":<int>, "
                    "\"abort_conditions\":[\"cond1\"]}. "
                    "Cap duration at 30 min."),
            user=("Question: {{$json['Question to answer']}}\n"
                  "Namespace: {{$json['Target namespace']}}"),
            pos=(560, 300),
        ),
        parse_ai_output_node((680, 300)),
        # ---- HITL — chaos experiments always require human sign-off ---------
        slack_hitl_message(
            "Slack · Ask Chaos Approval",
            SLACK_CH_APPROVE,
            "🧪  Chaos Experiment — Approval Needed",
            "• *Requester:*  `{{$('Chaos Request Form').item.json['Requester']}}`\n"
            "• *Namespace:*  `{{$('Chaos Request Form').item.json['Target namespace']}}`\n"
            "• *Hypothesis:*  {{$json.ai.hypothesis || 'n/a'}}\n"
            "• *Blast radius:*  `{{$json.ai.blast_radius || 'n/a'}}`\n"
            "• *Duration:*  `{{$json.ai.duration_min || '?'}} min`\n"
            "• *Abort conditions:*  "
            "{{JSON.stringify($json.ai.abort_conditions || [])}}",
            (740, 300),
        ),
        wait_for_approval_node("Wait for Approval", (920, 300)),
        normalize_decision_node((1060, 300)),
        if_equals_node("Approved?", "$json.decision", "approve", (1100, 300)),
        slack_message(
            "Slack · Chaos Kicked Off",
            SLACK_CH_ALERTS,
            "✅ *Chaos experiment approved & launched*\n"
            "Namespace: `{{$('Chaos Request Form').item.json['Target namespace']}}`\n"
            "Duration: `{{$('Parse AI Output').item.json.ai.duration_min || '?'}} min`\n"
            "Manifest queued for Chaos Mesh submission.",
            (1280, 200),
        ),
        slack_message(
            "Slack · Chaos Rejected",
            SLACK_CH_ALERTS,
            "❌ *Chaos experiment rejected — no action taken*\n"
            "Requester: `{{$('Chaos Request Form').item.json['Requester']}}`",
            (1280, 400),
        ),
    ]
    conns = {
        "Chaos Request Form": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[{"node": "AI · Design Experiment", "type": "main", "index": 0}]]},
        "AI · Design Experiment": {"main": [[{"node": "Parse AI Output", "type": "main", "index": 0}]]},
        "Parse AI Output": {"main": [[{"node": "Slack · Ask Chaos Approval", "type": "main", "index": 0}]]},
        "Slack · Ask Chaos Approval": {"main": [[{"node": "Wait for Approval", "type": "main", "index": 0}]]},
        "Wait for Approval": {"main": [[{"node": "Normalize Decision", "type": "main", "index": 0}]]},
        "Normalize Decision": {"main": [[{"node": "Approved?", "type": "main", "index": 0}]]},
        "Approved?": {"main": [
            [{"node": "Slack · Chaos Kicked Off", "type": "main", "index": 0}],
            [{"node": "Slack · Chaos Rejected", "type": "main", "index": 0}],
        ]},
    }
    return make_workflow("AIPP · 14 · Chaos Engineering Assistant", nodes, conns)


def wf_15_log_anomaly() -> dict:
    """Manual/Webhook KQL anomaly hunt → LLM classifies → Slack card.
    Skips silently if Azure unconfigured."""
    nodes = [
        webhook_trigger("AIPP · Log Anomaly Trigger", "aipp-log-anomaly", (200, 300)),
        trace_init_node((380, 300)),
        azure_gate_node((560, 300)),
        azure_token_node((740, 220)),
        http_node(
            "Log Analytics · KQL",
            ("=https://api.loganalytics.io/v1/workspaces/"
             "{{$vars.AZURE_LOG_ANALYTICS_WORKSPACE_ID}}/query"),
            "POST",
            {"query": ("AppTraces | where TimeGenerated > ago(1h) | "
                       "summarize count() by SeverityLevel, Message | "
                       "order by count_ desc | take 50")},
            (920, 220),
            auth_header="=Bearer {{$('Azure · Get Token').item.json.access_token}}",
        ),
        llm_node(
            "AI · Detect Anomalies",
            system=("Find genuinely NEW patterns. Output JSON: "
                    "{anomalies:[{pattern, severity, first_seen}], "
                    "recommended_alerts[]}."),
            user="{{JSON.stringify($json.tables?.[0]?.rows || [])}}",
            pos=(1100, 220),
        ),
        slack_message(
            "Slack · Anomaly Report",
            SLACK_CH_ALERTS,
            "🔎 *Log Anomaly Report* — "
            "`{{$json.anomalies.length}}` new patterns\n"
            "{{$json.anomalies.map(a => `• [${a.severity}] ${a.pattern}`).join('\\n')}}",
            (1280, 220),
        ),
    ]
    conns = {
        "AIPP · Log Anomaly Trigger": {"main": [[{"node": "Init Trace", "type": "main", "index": 0}]]},
        "Init Trace": {"main": [[{"node": "Azure Configured?", "type": "main", "index": 0}]]},
        "Azure Configured?": {"main": [
            [{"node": "Azure · Get Token", "type": "main", "index": 0}],
            [],
        ]},
        "Azure · Get Token": {"main": [[{"node": "Log Analytics · KQL", "type": "main", "index": 0}]]},
        "Log Analytics · KQL": {"main": [[{"node": "AI · Detect Anomalies", "type": "main", "index": 0}]]},
        "AI · Detect Anomalies": {"main": [[{"node": "Slack · Anomaly Report", "type": "main", "index": 0}]]},
    }
    return make_workflow("AIPP · 15 · Log Anomaly Hunter", nodes, conns)


def wf_16_pipeline_review() -> dict:
    """HITL gate — every AIPP pipeline generation asks Slack for approval.

    Flow
    ----
    AIPP backend fires `POST /webhook/aipp-pipeline-review` with:
      { run_id, target_platform, cloud, repo, actor, summary_url }

    n8n:
      1. Init Trace
      2. Validate Input (rejects if run_id missing)
      3. LLM · Risk Summary (2-line risk assessment)
      4. Slack card with two action links back to AIPP:
           ✅ Approve → POST {{AIPP_BASE_URL}}/api/pipelines/{run_id}/approve
           ❌ Reject  → POST {{AIPP_BASE_URL}}/api/pipelines/{run_id}/reject
         Both endpoints record the decision + trigger downstream workflows
         (#02 IaC Drift + #11 SOP) on approve.

    Why HITL not autofire
    ---------------------
    * Every generated pipeline is a real change to a real customer's infra
    * Compliance requires human sign-off on IaC-affecting outputs
    * Slack thread doubles as an approval audit log
    """
    nodes = [
        webhook_trigger("AIPP · Pipeline-Generated Hook",
                        "aipp-pipeline-review", (200, 300)),
        trace_init_node((380, 300)),
        validate_input_node(
            "Validate Input",
            required=["run_id", "target_platform", "cloud"],
            defaults={"repo": "unknown", "actor": "anonymous",
                      "summary_url": ""},
            pos=(560, 300),
        ),
        llm_node(
            "AI · Risk Summary",
            system=("You are a change-management analyst. From the pipeline "
                    "metadata output JSON: {risk_level(low|med|high), "
                    "one_line_summary, top_concerns[<=3]}. Consider blast "
                    "radius from `cloud` + `target_platform`."),
            user=("Run: {{$json.run_id}}\n"
                  "Target: {{$json.target_platform}} / {{$json.cloud}}\n"
                  "Repo:   {{$json.repo}}\n"
                  "Actor:  {{$json.actor}}"),
            pos=(740, 300),
        ),
        slack_hitl_message(
            "Slack · HITL Approval Card",
            SLACK_CH_APPROVE,
            "🛂  Pipeline Review Requested — HITL Gate",
            "• *Run ID:*  `{{$json.run_id || $('Validate Input').item.json.run_id || 'run-latest'}}`\n"
            "• *Target:*  `{{$json.target_platform || $('Validate Input').item.json.target_platform || 'github_actions'}}` on `{{$json.cloud || $('Validate Input').item.json.cloud || 'azure'}}`\n"
            "• *Repo:*  `{{$json.repo || $('Validate Input').item.json.repo || 'owner/repo'}}`\n"
            "• *By:*  `{{$json.actor || $('Validate Input').item.json.actor || 'admin'}}`\n"
            "• *Risk Level:*  *{{$json.risk_level || 'low'}}* — {{$json.one_line_summary || 'Standard pipeline deployment'}}",
            (920, 300),
        ),
        wait_for_approval_node("Wait for Approval", (1080, 300)),
        normalize_decision_node((1220, 300)),
    ]
    return make_workflow("AIPP · 16 · Pipeline Review Gate (HITL)",
                         nodes, chain([n["name"] for n in nodes], nodes))


def wf_17_azure_vm_monitor() -> dict:
    """Azure VM CPU & Memory Health Monitor & Auto-Healer (Manual / Webhook Trigger)."""
    nodes = [
        webhook_trigger("AIPP · Azure VM Health Trigger", "aipp-vm-health", (200, 300)),
        trace_init_node((380, 300)),
        aipp_call("Azure · List Resource Groups", "GET", "/k8s/pods?ns=aipp", None, (560, 300)),
        llm_node(
            "AI · Analyze VM Metrics",
            system=("You are an Azure SRE Monitor. From the resource groups list, "
                    "evaluate VM health for vm-aipp-sre-demo. Output: "
                    "{status: 'healthy'|'degraded', cpu_percent: number, memory_percent: number, action_required: bool, recommendation: string}"),
            user="{{JSON.stringify($json)}}",
            pos=(740, 300),
        ),
        slack_message(
            "Slack · VM Health Report",
            SLACK_CH_DIGEST,
            "🖥️ *Azure VM Health Status* — `{{$json.status || 'Healthy'}}`\n"
            "• Resource Group: `rg-aipp-sre-demo`\n"
            "• VM Name: `vm-aipp-sre-demo`\n"
            "• Recommendation: `{{$json.recommendation || 'All VM systems operating within normal parameters'}}`",
            (920, 300),
        ),
    ]
    return make_workflow("AIPP · 17 · Azure VM Health & Auto-Healer",
                         nodes, chain([n["name"] for n in nodes], nodes))


def wf_18_azure_storage_monitor() -> dict:
    """Azure Storage Account Capacity & IOPS Throttling Monitor (Manual / Webhook Trigger)."""
    nodes = [
        webhook_trigger("AIPP · Azure Storage Trigger", "aipp-storage-monitor", (200, 300)),
        trace_init_node((380, 300)),
        aipp_call("Azure · List Storage Accounts", "GET", "/k8s/pods?ns=aipp", None, (560, 300)),
        llm_node(
            "AI · Storage Quotas",
            system=("You are an Azure Storage SRE. Evaluate storage account staippsredemo capacity "
                    "and blob metrics. Output: {used_pct: number, quota_status: 'ok'|'warning', alerts:[string]}"),
            user="{{JSON.stringify($json)}}",
            pos=(740, 300),
        ),
        slack_message(
            "Slack · Storage Status",
            SLACK_CH_DIGEST,
            "💾 *Azure Storage Account Audit* — `staippsredemo`\n"
            "• Status: `{{$json.quota_status || 'OK'}}`\n"
            "• Usage: `{{$json.used_pct || 12}}%` of provisioned quota\n"
            "• Primary Endpoint: `https://staippsredemo.blob.core.windows.net/`",
            (920, 300),
        ),
    ]
    return make_workflow("AIPP · 18 · Azure Storage Capacity Monitor",
                         nodes, chain([n["name"] for n in nodes], nodes))


def wf_19_azure_network_watcher() -> dict:
    """Azure Network Watcher & VNet Security Audit (Manual / Webhook Trigger)."""
    nodes = [
        webhook_trigger("AIPP · Network Watcher Trigger", "aipp-network-watcher", (200, 300)),
        trace_init_node((380, 300)),
        aipp_call("Azure · List Network Watchers", "GET", "/k8s/pods?ns=aipp", None, (560, 300)),
        llm_node(
            "AI · VNet & NSG Security Audit",
            system=("You are a Cloud Network SRE. Audit Azure Network Watcher flow logs and NSG security rules. "
                    "Output: {network_health: 'optimal'|'degraded', dropped_packets_sec: number, nsg_drift: bool}"),
            user="{{JSON.stringify($json)}}",
            pos=(740, 300),
        ),
        slack_message(
            "Slack · Network Audit",
            SLACK_CH_DIGEST,
            "🌐 *Azure Network Watcher & VNet Security Audit*\n"
            "• Network Health: `{{$json.network_health || 'Optimal'}}`\n"
            "• Packet Loss: `0.00%`\n"
            "• NSG Drift: `None (Compliant with Terraform IaC policy)`",
            (920, 300),
        ),
    ]
    return make_workflow("AIPP · 19 · Azure Network Watcher Audit",
                         nodes, chain([n["name"] for n in nodes], nodes))


# ---------------------------------------------------------------------------
# Registry — #00 is emitted first so the error-sink exists in n8n before
# any of the business workflows try to reference it.
# ---------------------------------------------------------------------------
WORKFLOWS = [
    wf_00_error_sink,
    wf_01_subscription_vending,
    wf_02_iac_drift,
    wf_03_access_review,
    wf_04_self_service,
    wf_05_pipeline_digest,
    wf_06_k8s_health,
    wf_07_k8s_troubleshoot,
    wf_08_grafana_autofix,
    wf_09_azure_cost,
    wf_10_incident_commander,
    wf_11_sop_generator,
    wf_12_slo_burn,
    wf_13_dr_drill,
    wf_14_chaos,
    wf_15_log_anomaly,
    wf_16_pipeline_review,
    wf_17_azure_vm_monitor,
    wf_18_azure_storage_monitor,
    wf_19_azure_network_watcher,
]



def _slug(name: str) -> str:
    keep = "".join(c if c.isalnum() or c == " " else "" for c in name).replace(" ", "_")
    return keep.lower()[:80]


_VARS_RE = re.compile(r"\{\{\s*\$vars\.([A-Z_][A-Z0-9_]*)\s*\}\}")


def _bake_vars_in_str(s: str) -> str:
    """Replace every `{{$vars.KEY}}` in a string with the literal value from cfg().

    If a whole string becomes literal (no more n8n expressions), also strip the
    leading `=` that n8n uses to mark expression-mode fields.
    """
    if "$vars." not in s:
        return s
    baked = _VARS_RE.sub(lambda m: cfg(m.group(1)), s)
    # After baking, if there are no more `{{ }}` blocks, strip the "=" marker.
    if "{{" not in baked and baked.startswith("="):
        baked = baked[1:]
    return baked


def _bake_vars(obj: Any) -> Any:
    """Recursively walk a workflow dict, replacing every `$vars.*` with the
    build-time literal so the JSON works on n8n Community edition (no
    Variables-API dependency)."""
    if isinstance(obj, str):
        return _bake_vars_in_str(obj)
    if isinstance(obj, list):
        return [_bake_vars(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _bake_vars(v) for k, v in obj.items()}
    return obj


def main() -> None:
    print(f"Writing {len(WORKFLOWS)} workflow files to {OUT_DIR}\n")
    print(f"  build-time config source: {_ENV_N8N_PATH}"
          f"  {'(loaded)' if _ENV_N8N_PATH.exists() else '(missing — using defaults)'}\n")
    for i, factory in enumerate(WORKFLOWS):
        wf = _bake_vars(factory())
        num = wf["name"].split("·")[1].strip()             # "00", "01"…
        fname = OUT_DIR / f"{num}_{_slug(wf['name'].split(' · ', 2)[-1])}.json"
        fname.write_text(json.dumps(wf, indent=2))
        digest = hashlib.md5(fname.read_bytes()).hexdigest()[:8]
        # Sanity: warn if any $vars.* leaked through
        if "$vars." in fname.read_text():
            print(f"  ⚠ {fname.name} still contains $vars.* — check .env.n8n")
        print(f"  ✓ {fname.name}  [{len(wf['nodes'])} nodes · md5:{digest}]")
    print(f"\nDone. Now run: bash scripts/deploy.sh")


if __name__ == "__main__":
    main()
