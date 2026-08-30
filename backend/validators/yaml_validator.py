"""YAML syntactic validator (does the string parse as YAML?)."""

from __future__ import annotations

from typing import Tuple

import yaml


class YAMLValidator:
    def check(self, content: str) -> Tuple[bool, str]:
        try:
            docs = list(yaml.safe_load_all(content))
            if not docs:
                return False, "empty YAML"
            return True, f"parsed {len(docs)} document(s)"
        except yaml.YAMLError as e:
            return False, f"YAML syntax error: {e}"
