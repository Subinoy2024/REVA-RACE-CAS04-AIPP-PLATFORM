"""Secret scanner — refuses to persist or commit YAML containing likely
secrets (API keys, tokens, private keys, passwords in plain text).

Why this exists:
  - LLM-generated YAML can sometimes echo user prompt content that
    accidentally includes secret-shaped strings.
  - Users pasting "custom deployment requirement" text might leak an env
    var value in the prompt, which then bleeds into a `#` comment in the
    generated YAML.
  - Committing that to GitHub is a P0 security incident. This scanner
    stops it before the commit endpoint touches the repo.

Where it runs:
  1. In `PipelineService.generate()` immediately after YAML is produced —
     result is annotated with `security_scan` so the UI can warn.
  2. In `POST /api/deployment/commit` — HARD-FAILS the commit if findings.

How it works:
  - Pure regex, deterministic, zero external calls.
  - Patterns are ordered by specificity: high-confidence tokens first.
  - Returns a list of findings + a boolean `blocked`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class SecretFinding:
    kind: str          # e.g. "github_pat", "aws_access_key"
    line: int          # 1-based line number in the input text
    snippet: str       # a redacted preview (first 12 chars + '...')
    severity: str      # "high" | "medium"


# Ordered from most specific → least specific. First match wins per line.
_PATTERNS: list[tuple[str, str, str]] = [
    ("github_pat",         r"gh[pousr]_[A-Za-z0-9]{36,}",                        "high"),
    ("github_pat_new",     r"github_pat_[A-Za-z0-9_]{22,}",                      "high"),
    ("aws_access_key",     r"\bAKIA[0-9A-Z]{16}\b",                              "high"),
    ("aws_secret_key",     r"(?i)aws.{0,20}secret.{0,20}['\"][A-Za-z0-9/+=]{40}['\"]", "high"),
    ("gcp_service_account", r"\"type\"\s*:\s*\"service_account\"",              "high"),
    ("private_key_pem",    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",                "high"),
    ("slack_token",        r"xox[baprs]-[A-Za-z0-9-]{10,}",                      "high"),
    ("stripe_key",         r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{20,}",     "high"),
    ("openai_key",         r"\bsk-[A-Za-z0-9]{20,}\b",                           "high"),
    ("azure_conn_string",  r"DefaultEndpointsProtocol=https?;AccountName=",      "high"),
    ("hardcoded_password", r"(?i)(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"$\{]{6,}['\"]",  "medium"),
]


# YAML placeholders that are legitimately used and should NOT trigger.
# Common in generated pipelines and in this project's own generators.
_SAFE_TOKENS = (
    "$(", "${", "{{",                    # ADO / GH Actions / Harness vars
    "REPLACE_ME", "CHANGE_ME", "<YOUR",  # obvious placeholders
    "example.com",
)


def _looks_safe(match_text: str) -> bool:
    """Heuristic: skip obvious placeholders and templated expressions."""
    return any(t in match_text for t in _SAFE_TOKENS)


def scan(text: str) -> List[SecretFinding]:
    """Return the list of secret findings in `text`. Empty list = clean."""
    if not text:
        return []
    out: List[SecretFinding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pat, severity in _PATTERNS:
            m = re.search(pat, line)
            if not m:
                continue
            matched = m.group(0)
            if _looks_safe(line):
                continue
            snippet = (matched[:12] + "…") if len(matched) > 13 else matched
            out.append(SecretFinding(kind=kind, line=lineno, snippet=snippet, severity=severity))
            break     # one finding per line is enough
    return out


def scan_report(text: str) -> dict:
    """JSON-safe report used by the API layer."""
    findings = scan(text)
    high = sum(1 for f in findings if f.severity == "high")
    return {
        "clean": len(findings) == 0,
        "blocked": high > 0,
        "findings": [
            {"kind": f.kind, "line": f.line, "snippet": f.snippet, "severity": f.severity}
            for f in findings
        ],
    }
