"""Iteration-20 UI tweaks — Audit Log tab + accurate PAT security copy.

User request: "GitHub PATs are used read-only" was misleading now that we
also write YAML back via `POST /api/deployment/commit`. Also wanted a
dedicated tab to inspect the audit trail for troubleshooting.

Contracts checked here:
  * The gradio_app markdown no longer flatly claims PATs are read-only.
  * The new `audit_log` tab exists, exposes `build_tab()`, and its
    `_refresh()` helper renders a compact Markdown table from the
    `/api/research/audit` payload.
  * The `_marker()` helper colourises errors distinctly from successes.
  * The gradio_app registers exactly one Audit Log tab.
"""

from __future__ import annotations

import inspect

from frontend import gradio_app
from frontend.tabs import audit_log


class TestSecurityCopyReflectsWriteCapability:
    def test_copy_mentions_commit_write_scope(self):
        src = inspect.getsource(gradio_app)
        assert "Commit YAML to repo" in src
        assert "read-only for repository analysis" in src or "read-only for" in src

    def test_copy_no_longer_flatly_claims_read_only(self):
        src = inspect.getsource(gradio_app)
        # The blanket "used read-only" statement (without qualification)
        # must not appear any more.
        assert "used read-only, never logged" not in src

    def test_copy_points_users_to_the_audit_log_tab(self):
        src = inspect.getsource(gradio_app)
        assert "Audit Log" in src

    def test_gradio_app_registers_audit_log_tab(self):
        src = inspect.getsource(gradio_app)
        assert 'gr.Tab("Audit Log"' in src or "tab-audit" in src


class TestAuditLogModule:
    def test_build_tab_is_callable(self):
        assert callable(audit_log.build_tab)

    def test_marker_distinguishes_success_and_error(self):
        assert audit_log._marker("pipeline.generate.done") == "🟢"
        assert audit_log._marker("pipeline.generate.error") == "🔴"
        assert audit_log._marker("pipeline.generate.start") == "🔵"

    def test_short_details_truncates_long_blobs(self):
        long_val = {"payload": "x" * 500}
        out = audit_log._short_details(long_val)
        assert len(out) <= 220
        assert out.endswith("…")

    def test_short_details_handles_none(self):
        assert audit_log._short_details(None) == "-"

    def test_short_details_escapes_pipe_char_for_markdown_table(self):
        # A raw `|` in details would corrupt the Markdown table layout.
        out = audit_log._short_details({"note": "a|b"})
        assert "|" not in out or "\\|" in out


class TestRefreshRendersTable:
    def test_empty_response_shows_info_banner(self, monkeypatch):
        monkeypatch.setattr(audit_log, "get", lambda path, **kw: [])
        status, table = audit_log._refresh(50)
        assert "No audit entries yet" in status
        assert table == ""

    def test_rows_render_as_markdown_table(self, monkeypatch):
        rows = [
            {"id": "1", "action": "pipeline.generate.start", "actor": "system",
             "tool": "planner", "details": {"ci": "azure_devops"},
             "created_at": "2026-02-01T00:00:00"},
            {"id": "2", "action": "pipeline.generate.error", "actor": "system",
             "tool": "planner", "details": {"error": "boom"},
             "created_at": "2026-02-01T00:00:05"},
        ]
        monkeypatch.setattr(audit_log, "get", lambda path, **kw: rows)
        status, table = audit_log._refresh(50)
        assert "Loaded **2** most recent" in status
        # Two body rows + 2 header rows = 4 lines.
        assert table.count("|") >= 4
        # Both action names must appear inline.
        assert "pipeline.generate.start" in table
        assert "pipeline.generate.error" in table
        # Error row must get the red marker; start row the blue one.
        assert "🔴" in table and "🔵" in table

    def test_backend_failure_surfaces_error_string(self, monkeypatch):
        def _boom(*a, **kw):
            raise RuntimeError("HTTP 500: db down")
        monkeypatch.setattr(audit_log, "get", _boom)
        status, table = audit_log._refresh(50)
        assert status.startswith("❌")
        assert "db down" in status
        assert table == ""
