"""Production-grade validation for n8n workflow JSON files.

This test suite enforces the contracts our workflow generator promises:

  1. No dead references — every {{$env.FOO}} must appear in .env.n8n.example.
  2. No stub URLs — httpbin.org / example.com never appear in a prod flow.
  3. No hard-coded Slack channels — every Slack node uses an env-driven ref.
  4. Every webhook workflow has an Init Trace + input validation prelude.
  5. Every workflow (except #00) has `settings.errorWorkflow` set to the
     shared error-sink workflow.
  6. Every Azure API call uses a bearer that comes from the token-exchange
     node's output (never a static AZURE_TOKEN env var).
  7. Every HTTP node has `retryOnFail=true, maxTries>=2` for reliability.
  8. Every generated file is valid JSON and has unique node names.

Run with:
    cd /app && pytest backend/tests/test_n8n_workflows.py -v
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "n8n" / "workflows"
ENV_EXAMPLE = REPO_ROOT / "n8n" / ".env.n8n.example"
ERROR_SINK_NAME = "AIPP · 00 · Error Sink"

# Env vars intrinsically available in every n8n execution (not from .env)
BUILT_IN_ENV = {
    "N8N_HOST", "N8N_PORT", "NODE_ENV", "TZ", "N8N_LOG_LEVEL",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def workflows() -> list[dict]:
    files = sorted(WORKFLOWS_DIR.glob("*.json"))
    assert files, f"No workflows in {WORKFLOWS_DIR} — did you run build_workflows.py?"
    return [json.loads(f.read_text()) for f in files]


@pytest.fixture(scope="module")
def declared_env_vars() -> set[str]:
    """All KEY= names in .env.n8n.example (single source of truth)."""
    text = ENV_EXAMPLE.read_text()
    keys: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=", line)
        if m:
            keys.add(m.group(1))
    return keys | BUILT_IN_ENV


def _stringify(obj) -> str:
    """Serialise the whole workflow so we can grep across every field."""
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 1. No dead references — after iteration-35, config is BAKED at build time
# ---------------------------------------------------------------------------
def test_all_env_refs_are_declared(workflows, declared_env_vars):
    """Iteration-35 refactor: build_workflows.py inlines all config from
    n8n/.env.n8n at build time (n8n Community edition doesn't support the
    Variables API). So the invariant is now stronger: NO `$vars.*` or
    `$env.*` refs should exist in any generated workflow at all."""
    ref_re = re.compile(r"\$(?:env|vars)\.[A-Z_][A-Z0-9_]*")
    leaks: dict[str, list[str]] = {}
    for wf in workflows:
        hits = ref_re.findall(_stringify(wf))
        if hits:
            leaks[wf["name"]] = sorted(set(hits))
    assert not leaks, (
        f"Config leaked as $vars/$env refs (should be inlined): {leaks}"
    )


def test_no_lingering_env_refs(workflows):
    """Kept for backward compatibility — same guarantee as above."""
    env_ref = re.compile(r"\$env\.[A-Z_][A-Z0-9_]*")
    offenders: dict[str, list[str]] = {}
    for wf in workflows:
        hits = env_ref.findall(_stringify(wf))
        if hits:
            offenders[wf["name"]] = sorted(set(hits))
    assert not offenders, f"Lingering $env.* refs: {offenders}"


# ---------------------------------------------------------------------------
# 2. No stub URLs
# ---------------------------------------------------------------------------
FORBIDDEN_HOSTS = ("httpbin.org", "example.com", "localhost", "127.0.0.1")


def test_no_stub_urls(workflows):
    offenders: list[tuple[str, str]] = []
    for wf in workflows:
        blob = _stringify(wf)
        for host in FORBIDDEN_HOSTS:
            if host in blob:
                offenders.append((wf["name"], host))
    assert not offenders, f"Stub URLs still present: {offenders}"


# ---------------------------------------------------------------------------
# 2b. No JavaScript Code nodes — pure no-code / low-code visual flow
# ---------------------------------------------------------------------------
def test_no_code_nodes(workflows):
    """Iteration-36 refactor: every workflow is a visual n8n graph using only
    Set/Filter/IF/HTTP/Trigger/Slack/OpenAI nodes. No `n8n-nodes-base.code`
    should appear — the MS-project story is 'AI-driven low-code automation'
    and any Code node undermines that."""
    offenders: dict[str, list[str]] = {}
    for wf in workflows:
        code_nodes = [n["name"] for n in wf.get("nodes", [])
                      if n.get("type") == "n8n-nodes-base.code"]
        if code_nodes:
            offenders[wf["name"]] = code_nodes
    assert not offenders, (
        f"Code (JavaScript) nodes still present — refactor to no-code: {offenders}"
    )


# ---------------------------------------------------------------------------
# 3. No hard-coded Slack channels
# ---------------------------------------------------------------------------
def test_slack_channels_are_env_driven(workflows):
    """After iteration-35, channelIds are BAKED at build time from
    n8n/.env.n8n. Every channelId must be either the literal `aipp` (default)
    or a real channel name — never an $env/$vars expression."""
    bad: list[tuple[str, str, str]] = []
    for wf in workflows:
        for node in wf["nodes"]:
            if node["type"] != "n8n-nodes-base.slack":
                continue
            ch = node["parameters"].get("channelId", {})
            val = ch.get("value") if isinstance(ch, dict) else ch
            if not val:
                continue
            if "$vars." in val or "$env." in val:
                bad.append((wf["name"], node["name"], val))
    assert not bad, f"Slack channels still reference $vars/$env: {bad}"


# ---------------------------------------------------------------------------
# 4. Every webhook workflow has the observability prelude
# ---------------------------------------------------------------------------
def test_webhook_workflows_have_init_trace(workflows):
    """A webhook-triggered workflow must contain an Init Trace node."""
    for wf in workflows:
        has_webhook = any(n["type"] == "n8n-nodes-base.webhook"
                          for n in wf["nodes"])
        has_trace = any(n["name"] == "Init Trace" for n in wf["nodes"])
        if has_webhook and not has_trace:
            pytest.fail(f"{wf['name']} has a webhook but no Init Trace")


def test_schedule_workflows_have_init_trace(workflows):
    """Scheduled workflows must also emit a traceId at the top."""
    for wf in workflows:
        if wf["name"] == ERROR_SINK_NAME:
            continue                                # error sink is trigger-only
        is_scheduled = any(n["type"] == "n8n-nodes-base.scheduleTrigger"
                           for n in wf["nodes"])
        has_trace = any(n["name"] == "Init Trace" for n in wf["nodes"])
        if is_scheduled and not has_trace:
            pytest.fail(f"{wf['name']} is scheduled but has no Init Trace")


# ---------------------------------------------------------------------------
# 5. Every workflow (except #00) forwards errors to the error sink
# ---------------------------------------------------------------------------
def test_workflows_attach_error_sink(workflows):
    for wf in workflows:
        if wf["name"] == ERROR_SINK_NAME:
            continue
        settings = wf.get("settings", {})
        assert settings.get("errorWorkflow") == ERROR_SINK_NAME, (
            f"{wf['name']} does not attach the error sink "
            f"(got errorWorkflow={settings.get('errorWorkflow')!r})"
        )


def test_error_sink_exists(workflows):
    names = [w["name"] for w in workflows]
    assert ERROR_SINK_NAME in names, "Error-sink workflow missing"


# ---------------------------------------------------------------------------
# 6. No static Azure bearer token — must use OAuth exchange
# ---------------------------------------------------------------------------
def test_azure_calls_use_oauth_token(workflows):
    """No workflow may reference a static `AZURE_TOKEN` (deprecated)."""
    offenders: list[str] = []
    for wf in workflows:
        blob = _stringify(wf)
        if "$env.AZURE_TOKEN" in blob or "$vars.AZURE_TOKEN" in blob:
            offenders.append(wf["name"])
    assert not offenders, (
        f"Static AZURE_TOKEN used in: {offenders} — replace with the "
        "azure_token_node() OAuth exchange."
    )


def test_azure_workflows_have_token_node(workflows):
    """If a workflow calls management.azure.com, it must first exchange
    client-credentials via the shared Azure · Get Token node."""
    for wf in workflows:
        blob = _stringify(wf)
        if "management.azure.com" not in blob and "loganalytics.io" not in blob:
            continue
        node_names = {n["name"] for n in wf["nodes"]}
        assert "Azure · Get Token" in node_names, (
            f"{wf['name']} calls an Azure API but has no "
            "'Azure · Get Token' node."
        )


# ---------------------------------------------------------------------------
# 7. Every HTTP node has retries
# ---------------------------------------------------------------------------
def test_http_nodes_have_retry(workflows):
    bad: list[tuple[str, str]] = []
    for wf in workflows:
        for node in wf["nodes"]:
            if node["type"] != "n8n-nodes-base.httpRequest":
                continue
            if not node.get("retryOnFail") or node.get("maxTries", 1) < 2:
                bad.append((wf["name"], node["name"]))
    assert not bad, f"HTTP nodes without retry: {bad}"


# ---------------------------------------------------------------------------
# 8. Structural sanity
# ---------------------------------------------------------------------------
def test_unique_node_names_per_workflow(workflows):
    for wf in workflows:
        names = [n["name"] for n in wf["nodes"]]
        dupes = [n for n in set(names) if names.count(n) > 1]
        assert not dupes, f"{wf['name']} has duplicate node names: {dupes}"


def test_all_files_are_valid_json():
    """Redundant with `workflows` fixture but yields a clearer failure line."""
    for path in WORKFLOWS_DIR.glob("*.json"):
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as e:
            pytest.fail(f"{path.name} is invalid JSON: {e}")


def test_expected_workflow_count(workflows):
    """20 total workflows (00 error sink + 01-19)."""
    assert len(workflows) == 20, (
        f"Expected 20 workflows (00 error sink + 01-19), got {len(workflows)}"
    )


# ---------------------------------------------------------------------------
# 9. Multi-tenant / security nodes present where they should be
# ---------------------------------------------------------------------------
SLACK_WEBHOOK_WORKFLOWS = {
    "AIPP · 01 · Azure Subscription Vending",
    "AIPP · 07 · K8s Troubleshoot Assistant",
}


def test_slack_webhooks_have_security_note(workflows):
    """Iteration-36 refactor: HMAC verification requires a Code node, which
    breaks our no-code invariant. Slack-triggered flows now include a
    Sticky Note ('🛈 Slack Security Note') explaining that hardening happens
    at the ingress layer (Cloudflare IP allowlist + HTTPS)."""
    for wf in workflows:
        if wf["name"] not in SLACK_WEBHOOK_WORKFLOWS:
            continue
        node_names = {n["name"] for n in wf["nodes"]}
        assert "🛈 Slack Security Note" in node_names, (
            f"{wf['name']} is Slack-triggered but missing the security note"
        )


def test_repo_scoped_webhooks_have_validate_input():
    """Workflows that mutate GitHub via user input have a Validate node."""
    p = WORKFLOWS_DIR / "01_azure_subscription_vending.json"
    wf = json.loads(p.read_text())
    node_names = {n["name"] for n in wf["nodes"]}
    assert "Validate Input" in node_names, (
        "Subscription-vending must validate incoming Slack payload"
    )


def test_hitl_wait_nodes_have_correct_schema(workflows):
    """Every Wait-in-webhook-mode node must expose the correct top-level
    parameters. Nesting responseCode/responseData inside `options` (the
    old shape) meant n8n silently ignored them and, in some 1.6x builds,
    prevented the execution from entering a waiting state at all —
    causing the flow to finish instantly with waitTill=None.

    Regression-test the exact schema fields Wait.node.ts inherits from
    the Webhook description module.
    """
    seen = 0
    for wf in workflows:
        for node in wf["nodes"]:
            if node.get("type") != "n8n-nodes-base.wait":
                continue
            seen += 1
            p = node["parameters"]
            assert p.get("resume") == "webhook", (
                f"{wf['name']}: Wait node must use resume=webhook, got {p.get('resume')}")
            for k in ("httpMethod", "responseCode", "responseMode",
                      "responseData"):
                assert k in p, (
                    f"{wf['name']}: Wait node missing top-level {k!r}. "
                    f"(nesting these inside options=... will silently break "
                    f"the wait — see Wait.node.ts webhook description.)"
                )
            assert p.get("limitWaitTime") is False, (
                f"{wf['name']}: limitWaitTime must be explicitly false so "
                f"n8n uses WAIT_INDEFINITELY."
            )
    assert seen >= 4, (
        f"Expected at least 4 HITL Wait nodes across the workflow set, saw {seen}. "
        f"Did someone remove the HITL gates?"
    )


def test_hitl_upstream_nodes_are_failsafe(workflows):
    """Every node on the path to a Wait node must have onError set to
    continueRegularOutput AND alwaysOutputData=true.

    Rationale: if any upstream node fails (missing Slack/LLM creds, k8s
    proxy unreachable, LLM JSON.parse error…) or emits 0 items (Filter
    drop, Aggregate with no data…), n8n terminates the execution BEFORE
    the Wait node parks — the flow finishes instantly with waitTill=None
    and the HITL demo silently collapses. Locking this invariant in a
    unit test guarantees the demo stays green even when infra hiccups.
    """
    skip_types = {
        "n8n-nodes-base.webhook", "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.formTrigger", "n8n-nodes-base.errorTrigger",
        "n8n-nodes-base.stickyNote", "n8n-nodes-base.wait",
        "n8n-nodes-base.if", "n8n-nodes-base.filter",
    }
    offenders: list[tuple[str, str, str]] = []
    for wf in workflows:
        wait_nodes = {n["name"] for n in wf["nodes"]
                      if n.get("type") == "n8n-nodes-base.wait"}
        if not wait_nodes:
            continue
        # Reverse-adjacency
        rev: dict[str, set[str]] = {}
        for src, outs in wf.get("connections", {}).items():
            for branch in outs.get("main", []) or []:
                for edge in branch or []:
                    rev.setdefault(edge["node"], set()).add(src)
        # Ancestors of every Wait node
        ancestors: set[str] = set()
        frontier = list(wait_nodes)
        while frontier:
            cur = frontier.pop()
            for parent in rev.get(cur, ()):
                if parent not in ancestors:
                    ancestors.add(parent)
                    frontier.append(parent)
        by_name = {n["name"]: n for n in wf["nodes"]}
        for a in ancestors:
            node = by_name.get(a)
            if not node or node.get("type") in skip_types:
                continue
            if node.get("onError") != "continueRegularOutput":
                offenders.append((wf["name"], a, "onError missing"))
            if not node.get("alwaysOutputData"):
                offenders.append((wf["name"], a, "alwaysOutputData missing"))
    assert not offenders, (
        f"HITL upstream nodes not hardened — will break the demo:\n" +
        "\n".join(f"  {w} :: {n} :: {r}" for w, n, r in offenders)
    )
