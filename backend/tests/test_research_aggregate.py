"""Unit tests for the AIPP research batch aggregator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.research import aggregate


SAMPLE_RECORDS = [
    {
        "id": 1, "experiment_type": "aipp", "ci_platform": "github_actions",
        "repository_url": "https://github.com/pallets/flask",
        "metrics": {
            "generation_seconds": 8.5, "yaml_syntax_valid": True,
            "platform_schema_valid": True, "env_trigger_correct": True,
            "security_ok": True, "custom_requirement_addressed": True,
            "manual_corrections_estimated": 0,
        },
    },
    {
        "id": 2, "experiment_type": "aipp", "ci_platform": "azure_devops",
        "repository_url": "https://github.com/tiangolo/fastapi",
        "metrics": {
            "generation_seconds": 9.2, "yaml_syntax_valid": True,
            "platform_schema_valid": False, "env_trigger_correct": True,
            "security_ok": True, "custom_requirement_addressed": True,
            "manual_corrections_estimated": 1,
        },
    },
    {
        "id": 3, "experiment_type": "static_template",
        "ci_platform": "github_actions",
        "repository_url": "https://github.com/pallets/flask",
        "metrics": {
            "generation_seconds": 0.001, "yaml_syntax_valid": True,
            "platform_schema_valid": True, "env_trigger_correct": False,
            "custom_requirement_addressed": False,
            "manual_corrections_estimated": 3,
        },
    },
]


class TestFlatRow:
    def test_flatten_extracts_all_metric_keys(self):
        r = aggregate._flat_row(SAMPLE_RECORDS[0])
        assert r["variant"] == "aipp"
        assert r["repository_url"] == "https://github.com/pallets/flask"
        assert r["generation_seconds"] == 8.5
        assert r["yaml_syntax_valid"] is True
        assert r["manual_corrections_estimated"] == 0

    def test_flatten_missing_metrics_returns_none(self):
        r = aggregate._flat_row({"id": 99, "experiment_type": "aipp"})
        assert r["variant"] == "aipp"
        assert r["generation_seconds"] is None
        assert r["yaml_syntax_valid"] is None


class TestAggregateStatistics:
    def test_aggregate_computes_per_variant_means_and_pcts(self):
        flat = [aggregate._flat_row(r) for r in SAMPLE_RECORDS]
        summary = aggregate._aggregate(flat)
        assert set(summary.keys()) == {"aipp", "static_template"}
        aipp = summary["aipp"]
        assert aipp["n"] == 2
        # (8.5 + 9.2) / 2 = 8.85
        assert aipp["mean_generation_seconds"] == pytest.approx(8.85, abs=0.01)
        # 2/2 yaml syntax OK
        assert aipp["pct_yaml_syntax_valid"] == 100.0
        # 1/2 platform_schema OK
        assert aipp["pct_platform_schema_valid"] == 50.0

    def test_empty_input_returns_empty_summary(self):
        assert aggregate._aggregate([]) == {}


class TestMarkdownWriter:
    def test_write_markdown_produces_file_with_headers(self, tmp_path: Path):
        flat = [aggregate._flat_row(r) for r in SAMPLE_RECORDS]
        summary = aggregate._aggregate(flat)
        md = aggregate._write_markdown(tmp_path, summary, row_count=len(flat))
        assert md.exists()
        text = md.read_text(encoding="utf-8")
        assert "AIPP evaluation" in text
        assert "aipp" in text
        assert "| Variant |" in text


class TestMainOfflineDrivesFullPipeline:
    def test_main_input_json_writes_json_csv_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        in_path = tmp_path / "input.json"
        in_path.write_text(json.dumps(SAMPLE_RECORDS), encoding="utf-8")
        out_dir = tmp_path / "out"

        monkeypatch.setattr(
            "sys.argv",
            [
                "aggregate", "--out", str(out_dir),
                "--input-json", str(in_path),
            ],
        )
        rc = aggregate.main()
        assert rc == 0
        for name in ["results.json", "results.csv", "results.md"]:
            assert (out_dir / name).exists(), f"missing {name}"
        # results.csv must have the header + 3 data rows.
        csv_text = (out_dir / "results.csv").read_text(encoding="utf-8")
        assert csv_text.count("\n") >= 3
