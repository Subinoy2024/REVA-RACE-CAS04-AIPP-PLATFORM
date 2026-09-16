"""Read-only endpoint exposing the OPA policy bundle shipped with AIPP.

Powers the "OPA Live Preview" panel in the Pipeline Generator tab so users
know exactly which policy gates will fire during the `policy` stage of
their infra pipeline.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/policy", tags=["policy"])

_ROOT = Path("/app/policy")
if not _ROOT.is_dir():
    _ROOT = Path(__file__).resolve().parent.parent.parent / "policy"


@router.get("/bundle")
async def get_bundle() -> dict:
    """List the starter Rego rules shipped in /app/policy/, grouped by cloud."""
    clouds: dict[str, list[dict]] = {}
    if _ROOT.is_dir():
        for cloud_dir in sorted(p for p in _ROOT.iterdir() if p.is_dir()):
            clouds[cloud_dir.name] = [
                {
                    "file": rego.name,
                    "package": _first_package(rego),
                    "description": _first_comment(rego),
                }
                for rego in sorted(cloud_dir.glob("*.rego"))
            ]
    return {"root": str(_ROOT), "clouds": clouds}


def _first_comment(path: Path) -> str:
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("#") and len(line) > 1:
            return line.lstrip("# ").strip()
    return ""


def _first_package(path: Path) -> str:
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("package "):
            return line.split(" ", 1)[1].strip()
    return "?"
