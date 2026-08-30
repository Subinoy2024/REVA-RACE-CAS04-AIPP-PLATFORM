"""AIPP research batch aggregator.

Reads all experiment rows from the AIPP database via `/api/research/experiments`
and emits three artifacts for the thesis appendix:

  1. `results.json`  — raw per-run records
  2. `results.csv`   — flat table (one row per experiment)
  3. `results.md`    — markdown summary with variant-wise aggregates

Usage:
  python -m tests.research.aggregate --out tests/research/results/
  python -m tests.research.aggregate --out tests/research/results/ --base http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

import httpx


def _fetch_records(base: str) -> List[Dict[str, Any]]:
    r = httpx.get(f"{base.rstrip('/')}/api/research/experiments", timeout=60)
    r.raise_for_status()
    payload = r.json()
    # Support both `{"items": [...]}` and a raw list.
    if isinstance(payload, dict) and "items" in payload:
        return list(payload["items"])
    if isinstance(payload, list):
        return payload
    raise RuntimeError(f"Unexpected /api/research/experiments payload: {payload!r}")


def _flat_row(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one experiment record for CSV output."""
    metrics = rec.get("metrics") or {}
    return {
        "id": rec.get("id"),
        "variant": rec.get("experiment_type"),
        "ci_platform": rec.get("ci_platform"),
        "cloud_platform": (metrics.get("cloud_platform")
                           or rec.get("cloud_platform")),
        "repository_url": rec.get("repository_url"),
        "generation_seconds": metrics.get("generation_seconds"),
        "yaml_syntax_valid": metrics.get("yaml_syntax_valid"),
        "platform_schema_valid": metrics.get("platform_schema_valid"),
        "env_trigger_correct": metrics.get("env_trigger_correct"),
        "security_ok": metrics.get("security_ok"),
        "custom_requirement_addressed": metrics.get("custom_requirement_addressed"),
        "manual_corrections_estimated": metrics.get("manual_corrections_estimated"),
        "error": metrics.get("error"),
    }


def _aggregate(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Per-variant aggregate statistics."""
    by_variant: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_variant[r["variant"] or "unknown"].append(r)

    def _mean(vals: List[float]) -> float:
        vals = [v for v in vals if isinstance(v, (int, float))]
        return statistics.mean(vals) if vals else 0.0

    def _pct_true(vals: List[Any]) -> float:
        bools = [bool(v) for v in vals if v is not None]
        return 100.0 * sum(bools) / len(bools) if bools else 0.0

    summary: Dict[str, Dict[str, Any]] = {}
    for variant, items in sorted(by_variant.items()):
        summary[variant] = {
            "n": len(items),
            "mean_generation_seconds": round(
                _mean([i["generation_seconds"] for i in items]), 3
            ),
            "pct_yaml_syntax_valid": round(
                _pct_true([i["yaml_syntax_valid"] for i in items]), 1
            ),
            "pct_platform_schema_valid": round(
                _pct_true([i["platform_schema_valid"] for i in items]), 1
            ),
            "pct_env_trigger_correct": round(
                _pct_true([i["env_trigger_correct"] for i in items]), 1
            ),
            "pct_security_ok": round(
                _pct_true([i["security_ok"] for i in items]), 1
            ),
            "pct_custom_requirement_addressed": round(
                _pct_true([i["custom_requirement_addressed"] for i in items]), 1
            ),
            "mean_manual_corrections": round(
                _mean([i["manual_corrections_estimated"] for i in items]), 2
            ),
            "n_errors": sum(1 for i in items if i.get("error")),
        }
    return summary


def _write_markdown(out_dir: Path, summary: Dict[str, Dict[str, Any]],
                    row_count: int) -> Path:
    md = out_dir / "results.md"
    lines = [
        "# AIPP evaluation — batch run summary",
        "",
        f"Total experiment records: **{row_count}**",
        "",
        "## Per-variant aggregate",
        "",
        "| Variant | n | Mean gen (s) | YAML syntax OK | Schema OK | Env triggers OK | Security OK | Custom req addressed | Manual corrections | Errors |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for variant, s in summary.items():
        lines.append(
            "| {v} | {n} | {gs:.3f} | {ys:.1f}% | {ps:.1f}% | {et:.1f}% "
            "| {sec:.1f}% | {cr:.1f}% | {mc:.2f} | {er} |".format(
                v=variant, n=s["n"], gs=s["mean_generation_seconds"],
                ys=s["pct_yaml_syntax_valid"],
                ps=s["pct_platform_schema_valid"],
                et=s["pct_env_trigger_correct"],
                sec=s["pct_security_ok"],
                cr=s["pct_custom_requirement_addressed"],
                mc=s["mean_manual_corrections"], er=s["n_errors"],
            )
        )
    lines.append("")
    lines.append(
        "> Generated by `python -m tests.research.aggregate`. Use these figures "
        "in the thesis Evaluation chapter."
    )
    md.write_text("\n".join(lines), encoding="utf-8")
    return md


def main() -> int:
    parser = argparse.ArgumentParser(description="AIPP research aggregator")
    parser.add_argument("--out", type=Path, required=True,
                        help="Output directory for results.json/csv/md")
    parser.add_argument("--base", default="http://127.0.0.1:8001",
                        help="AIPP backend base URL")
    parser.add_argument("--input-json", type=Path,
                        help="Optional local JSON dump to aggregate instead "
                             "of calling the API (offline mode)")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    if args.input_json and args.input_json.exists():
        raw_records = json.loads(args.input_json.read_text(encoding="utf-8"))
    else:
        try:
            raw_records = _fetch_records(args.base)
        except Exception as e:
            print(f"Failed to fetch /api/research/experiments: {e}",
                  file=sys.stderr)
            return 2

    if not raw_records:
        print("No experiment records found. Run `run_batch.py` first.",
              file=sys.stderr)
        return 3

    # Write raw JSON
    (args.out / "results.json").write_text(
        json.dumps(raw_records, indent=2, default=str), encoding="utf-8"
    )

    # Flatten + write CSV
    flat = [_flat_row(r) for r in raw_records]
    if flat:
        with (args.out / "results.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(flat[0].keys()))
            writer.writeheader()
            writer.writerows(flat)

    # Write markdown summary
    summary = _aggregate(flat)
    md_path = _write_markdown(args.out, summary, row_count=len(flat))

    print(f"Wrote {len(flat)} experiment rows to {args.out}/")
    print(f"  - results.json  ({len(raw_records)} records)")
    print(f"  - results.csv   ({len(flat)} rows)")
    print(f"  - results.md    (summary: {md_path})")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
