"""Unit test for N8nService status parsing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.n8n_service import N8nService


@pytest.mark.asyncio
async def test_n8n_service_parses_statuses_correctly():
    fake_workflows = [
        {"id": "wf-1", "name": "Flow 1", "active": True, "nodes": [{"type": "n8n-nodes-base.webhook"}]},
        {"id": "wf-2", "name": "Flow 2", "active": True, "nodes": [{"type": "n8n-nodes-base.scheduleTrigger"}]},
        {"id": "wf-3", "name": "Flow 3", "active": True, "nodes": [{"type": "n8n-nodes-base.webhook"}]},
        {"id": "wf-4", "name": "Flow 4", "active": True, "nodes": [{"type": "n8n-nodes-base.webhook"}]},
    ]

    async def fake_call(domain, tool, **kwargs):
        if tool == "list_workflows":
            return fake_workflows
        if tool == "get_executions":
            wid = kwargs.get("workflow_id")
            if wid == "wf-1":
                return [{"id": "ex-1", "status": "success", "finished": True, "stoppedAt": "2026-08-27T10:00:00.000Z"}]
            if wid == "wf-2":
                return [{"id": "ex-2", "status": "error", "finished": False, "stoppedAt": "2026-08-27T10:05:00.000Z", "error": {"message": "Failed"}}]
            if wid == "wf-3":
                return [{"id": "ex-3", "status": "waiting", "finished": False, "startedAt": "2026-08-27T10:10:00.000Z"}]
            if wid == "wf-4":
                return [{"id": "ex-4", "status": "running", "finished": False, "startedAt": "2026-08-27T10:15:00.000Z"}]
        return []

    mock_mcp = MagicMock()
    mock_mcp.is_configured.return_value = True
    mock_mcp.call = fake_call

    with patch("backend.services.n8n_service.get_mcp_client", return_value=mock_mcp):
        res = await N8nService().status()
        assert res.configured is True
        wfs = {w.id: w for w in res.workflows}

        assert wfs["wf-1"].last_execution_status == "success"
        assert wfs["wf-1"].success is True

        assert wfs["wf-2"].last_execution_status == "error"
        assert wfs["wf-2"].success is False

        assert wfs["wf-3"].last_execution_status == "waiting"
        assert wfs["wf-3"].success is None

        assert wfs["wf-4"].last_execution_status == "running"
        assert wfs["wf-4"].success is None
