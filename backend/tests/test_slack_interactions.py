"""Tests for the Slack interactivity bridge — HITL button-click handling.

Covers:
  1. Signature verification (accepts a valid HMAC, rejects a bad one).
  2. Replay protection (rejects a stale timestamp).
  3. Missing-secret path (503 when SLACK_SIGNING_SECRET is unset).
  4. Happy path — POST with a valid signed payload triggers an n8n resume.
  5. Sanity: /api/slack/health always reachable, reports secret status.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.server import app

SIGNING_SECRET = "aipp-test-signing-secret"


def _sign(body: bytes, timestamp: str, secret: str = SIGNING_SECRET) -> str:
    base = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def _build_payload(action_id: str = "approve",
                   resume_url: str = "https://n8n.example.com/webhook-waiting/123?signature=abc",
                   ) -> bytes:
    body = {
        "type": "block_actions",
        "user": {"username": "vhs", "id": "U01"},
        "channel": {"id": "C01", "name": "aipp"},
        "message": {"text": "K8s Troubleshoot — Approval Needed"},
        "actions": [{
            "action_id": action_id,
            "value": resume_url,
            "type": "button",
        }],
    }
    return urllib.parse.urlencode({"payload": json.dumps(body)}).encode()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_health_endpoint_always_reachable(client):
    r = client.get("/api/slack/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["signing_secret_configured"] is True


def test_missing_secret_returns_503(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "")
    get_settings.cache_clear()
    body = _build_payload()
    ts = str(int(time.time()))
    with TestClient(app) as c:
        r = c.post(
            "/api/slack/interactions",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": "v0=fake",
            },
        )
    get_settings.cache_clear()
    assert r.status_code == 503


def test_bad_signature_rejected(client):
    body = _build_payload()
    ts = str(int(time.time()))
    r = client.post(
        "/api/slack/interactions",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": "v0=deadbeef",
        },
    )
    assert r.status_code == 401
    assert "bad signature" in r.json()["detail"].lower()


def test_stale_timestamp_rejected(client):
    body = _build_payload()
    # 10-minute-old timestamp — outside the 5-minute skew window.
    ts = str(int(time.time()) - 600)
    sig = _sign(body, ts)
    r = client.post(
        "/api/slack/interactions",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 401
    assert "stale" in r.json()["detail"].lower()


def test_valid_signature_forwards_to_n8n(client):
    """Happy path — a signed approve click should fire the n8n resume URL
    with ?a=approve appended, then return an `update` response_action so
    Slack replaces the message with the sealed audit card.
    """
    body = _build_payload(action_id="approve")
    ts = str(int(time.time()))
    sig = _sign(body, ts)

    # Mock the outbound httpx call so we don't actually try to reach n8n.
    fake_resp = AsyncMock()
    fake_resp.status_code = 200
    fake_resp.text = "Approval recorded"

    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.__aexit__.return_value = False
    async_client.get.return_value = fake_resp

    # Mock the audit-log write so this test doesn't need a running DB —
    # the dedicated `test_approvals_endpoint_persists_and_lists` test
    # covers the DB path with a real session.
    with patch("backend.api.slack.httpx.AsyncClient", return_value=async_client), \
         patch("backend.api.slack._audit") as mock_audit:
        mock_audit.log = AsyncMock()
        r = client.post(
            "/api/slack/interactions",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )

    assert r.status_code == 200
    resp = r.json()
    assert resp["response_action"] == "update"
    assert resp["replace_original"] is True

    # Verify the httpx call carried the correct resume URL + decision.
    called_url = async_client.get.await_args.args[0]
    assert "webhook-waiting/123" in called_url
    assert "a=approve" in called_url

    # And the sealed card mentions the clicking user.
    text_blob = json.dumps(resp["blocks"])
    assert "@vhs" in text_blob
    assert "Approved" in text_blob


def test_reject_action_forwards_correct_decision(client):
    body = _build_payload(action_id="reject")
    ts = str(int(time.time()))
    sig = _sign(body, ts)

    fake_resp = AsyncMock(status_code=200, text="ok")
    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.__aexit__.return_value = False
    async_client.get.return_value = fake_resp

    with patch("backend.api.slack.httpx.AsyncClient", return_value=async_client), \
         patch("backend.api.slack._audit") as mock_audit:
        mock_audit.log = AsyncMock()
        r = client.post(
            "/api/slack/interactions",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
    assert r.status_code == 200
    called_url = async_client.get.await_args.args[0]
    assert "a=reject" in called_url
    assert "Rejected" in json.dumps(r.json()["blocks"])


def test_bogus_action_id_rejected(client):
    body = _build_payload(action_id="hack")
    ts = str(int(time.time()))
    sig = _sign(body, ts)
    r = client.post(
        "/api/slack/interactions",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 400
    assert "unknown action_id" in r.json()["detail"].lower()


def test_button_value_must_be_a_resume_url(client):
    """A malicious app could plant an arbitrary URL in `value` — reject
    anything that doesn't look like an n8n resume URL."""
    body = _build_payload(resume_url="https://evil.example.com/pwn")
    ts = str(int(time.time()))
    sig = _sign(body, ts)
    r = client.post(
        "/api/slack/interactions",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 400
    assert "webhook-waiting" in r.json()["detail"]


def test_non_action_payload_gets_acked(client):
    """Slack also POSTs `view_submission`, `block_suggestion`, etc. to
    the same URL. We just ack them without doing anything n8n-related."""
    body = urllib.parse.urlencode({"payload": json.dumps({
        "type": "view_submission",
        "user": {"username": "vhs"},
        "view": {"id": "V01"},
    })}).encode()
    ts = str(int(time.time()))
    sig = _sign(body, ts)
    r = client.post(
        "/api/slack/interactions",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert r.status_code == 200
    resp = r.json()
    assert resp["ok"] is True and resp["ignored"] is True
    assert resp["type"] == "view_submission"


def test_click_writes_audit_log_entry(client):
    """Every valid HITL click must persist to audit_logs with the exact
    payload shape the /api/slack/approvals endpoint expects.
    """
    resume_url = ("https://n8n.example.com/webhook-waiting/9876"
                  "?signature=deadbeef")
    body = _build_payload(action_id="approve", resume_url=resume_url)
    ts = str(int(time.time()))
    sig = _sign(body, ts)

    fake_resp = AsyncMock(status_code=200, text="ok")
    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.__aexit__.return_value = False
    async_client.get.return_value = fake_resp

    with patch("backend.api.slack.httpx.AsyncClient", return_value=async_client), \
         patch("backend.api.slack._audit") as mock_audit:
        mock_audit.log = AsyncMock()
        r = client.post(
            "/api/slack/interactions",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
    assert r.status_code == 200
    mock_audit.log.assert_awaited_once()
    call = mock_audit.log.await_args
    assert call.kwargs["action"] == "slack.hitl.decision"
    assert call.kwargs["actor"] == "vhs"
    assert call.kwargs["tool"] == "slack"
    d = call.kwargs["details"]
    assert d["decision"] == "approve"
    assert d["slack_user"] == "vhs"
    assert d["slack_user_id"] == "U01"
    assert d["slack_channel"] == "aipp"
    assert d["n8n_execution_id"] == "9876"   # extracted from resume URL
    assert d["n8n_resume_status"] == 200
    assert "K8s Troubleshoot" in d["workflow_hint"]
    # CRITICAL: never persist the resume URL — it carries a resume token.
    for v in d.values():
        assert "signature=" not in str(v), (
            f"resume-URL signature leaked into audit payload: {d}")


def test_click_still_acks_slack_if_audit_write_fails(client):
    """DB hiccups must not cause Slack to retry (which would duplicate
    the resume call and confuse the audit trail)."""
    body = _build_payload(action_id="approve")
    ts = str(int(time.time()))
    sig = _sign(body, ts)

    fake_resp = AsyncMock(status_code=200, text="ok")
    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.__aexit__.return_value = False
    async_client.get.return_value = fake_resp

    with patch("backend.api.slack.httpx.AsyncClient", return_value=async_client), \
         patch("backend.api.slack._audit") as mock_audit:
        mock_audit.log = AsyncMock(side_effect=RuntimeError("db offline"))
        r = client.post(
            "/api/slack/interactions",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
    assert r.status_code == 200      # <-- must still ack Slack
    assert r.json()["response_action"] == "update"


def test_approvals_endpoint_shape_and_filters(client):
    """The /api/slack/approvals endpoint reads audit_logs and reshapes
    them into a UI-friendly list. Mock the DB read so we don't need a
    live Postgres in the test pod.
    """
    from unittest.mock import MagicMock

    from backend.database.models import AuditLog

    fake_row = MagicMock(spec=AuditLog)
    fake_row.id = "fake-uuid-1"
    fake_row.action = "slack.hitl.decision"
    fake_row.actor = "vhs"
    fake_row.tool = "slack"
    fake_row.details_json = {
        "decision": "approve",
        "slack_user": "vhs",
        "slack_user_id": "U01",
        "slack_channel": "aipp",
        "n8n_execution_id": "9876",
        "n8n_resume_status": 200,
        "workflow_hint": "K8s Troubleshoot — Approval Needed",
    }
    fake_row.created_at = datetime.now(timezone.utc)

    class _FakeExec:
        def scalars(self):
            class _S:
                @staticmethod
                def all():
                    return [fake_row]
            return _S()

    class _FakeSess:
        async def execute(self, *a, **kw):
            return _FakeExec()

    class _FakeCtx:
        async def __aenter__(self_inner):
            return _FakeSess()

        async def __aexit__(self_inner, *a):
            return False

    with patch("backend.api.slack.session_scope", return_value=_FakeCtx(),
               create=True):
        # `session_scope` is imported inside list_approvals — patch the
        # symbol on the module the endpoint pulls it from.
        with patch("backend.database.connection.session_scope",
                   return_value=_FakeCtx()):
            r = client.get("/api/slack/approvals?limit=25")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    row = body["approvals"][0]
    assert row["decision"] == "approve"
    assert row["user"] == "vhs"
    assert row["user_id"] == "U01"
    assert row["channel"] == "aipp"
    assert row["n8n_execution_id"] == "9876"
    assert row["n8n_status"] == 200
    assert "K8s Troubleshoot" in row["workflow_hint"]


def test_approvals_endpoint_rejects_bad_limit(client):
    """The limit is bounded to 1..500 to protect the DB. Test both edges."""
    assert client.get("/api/slack/approvals?limit=0").status_code == 422
    assert client.get("/api/slack/approvals?limit=501").status_code == 422
