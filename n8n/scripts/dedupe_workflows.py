#!/usr/bin/env python3
"""Dedupe AIPP workflows on the n8n server.

Some earlier deploy runs may have created multiple rows with the same
`AIPP · NN · ...` name. n8n allows duplicate names but only ONE of them
holds the active webhook path — usually the OLDER one, which means our
smoke-test's just-deployed workflow IDs never match the incoming
executions.

This script:
  1. Lists every workflow named `AIPP ·*`
  2. Groups by name
  3. Keeps the newest (by updatedAt, falls back to createdAt) and
     DELETES the rest
  4. Prints a per-row report

Env required:
  N8N_BASE_URL, N8N_API_KEY  — same as scripts/deploy.sh
"""
from __future__ import annotations

import collections
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("N8N_BASE_URL", "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY", "")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 AIPP-Dedupe"

if not BASE or not KEY:
    sys.exit("N8N_BASE_URL / N8N_API_KEY must be exported first "
             "(source ../.env && export N8N_BASE_URL N8N_API_KEY)")


def _get(path: str) -> dict:
    req = urllib.request.Request(
        BASE + path,
        headers={"X-N8N-API-KEY": KEY, "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _list_all_workflows() -> list[dict]:
    """Paginate — n8n caps `limit` at 250 on some builds so we walk
    `nextCursor` until the server stops returning one."""
    out: list[dict] = []
    cursor: str | None = None
    while True:
        path = "/api/v1/workflows?limit=250"
        if cursor:
            path += f"&cursor={urllib.parse.quote(cursor)}"
        d = _get(path)
        page = d.get("data") or (d if isinstance(d, list) else [])
        out.extend(page)
        cursor = d.get("nextCursor")
        if not cursor:
            break
    return out


def _delete(wid: str) -> tuple[bool, str]:
    req = urllib.request.Request(
        f"{BASE}/api/v1/workflows/{wid}",
        headers={"X-N8N-API-KEY": KEY, "User-Agent": UA},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, str(r.status)
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:120]}"


def main() -> int:
    wfs = _list_all_workflows()

    by_name: dict[str, list[dict]] = collections.defaultdict(list)
    for w in wfs:
        if (w.get("name") or "").startswith("AIPP"):
            by_name[w["name"]].append(w)

    dupes: list[tuple[str, dict, dict]] = []
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        # newest first — prefer updatedAt, fall back to createdAt
        group.sort(
            key=lambda w: (w.get("updatedAt") or w.get("createdAt") or ""),
            reverse=True,
        )
        keeper = group[0]
        for dup in group[1:]:
            dupes.append((name, dup, keeper))

    print(f"Scanned {len(wfs)} workflow(s). "
          f"Found {len(by_name)} unique AIPP name(s), "
          f"{len(dupes)} duplicate row(s) to delete.\n")

    if not dupes:
        print("Nothing to do — server is already clean.")
        return 0

    for name, dup, keeper in dupes:
        active = " (ACTIVE)" if dup.get("active") else ""
        print(f"  DELETE  {dup['id']:<20}{active}  "
              f"(keep {keeper['id']})   {name[:60]}")
        ok, msg = _delete(dup["id"])
        print(f"          {'✓ ' + msg if ok else '✗ ' + msg}")

    print(f"\nDone. Now re-run:  bash scripts/smoke_test_all.sh --local-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
