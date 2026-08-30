"""Security validator — refuses YAML that inlines obvious secrets or uses `curl | sh`."""

from __future__ import annotations

import re
from typing import Tuple


_DANGER = [
    (re.compile(r"curl[^|]*\|\s*(sudo\s+)?(sh|bash)"), "unauthenticated 'curl | sh' pattern"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key hard-coded in YAML"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "Google API key hard-coded in YAML"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub PAT hard-coded in YAML"),
    (re.compile(r"password\s*:\s*['\"][^'\"]{4,}['\"]", re.I), "hard-coded password in YAML"),
]


class SecurityValidator:
    def check(self, content: str) -> Tuple[bool, str]:
        for pat, msg in _DANGER:
            if pat.search(content):
                return False, msg
        return True, "no obvious secrets or unsafe patterns detected"
