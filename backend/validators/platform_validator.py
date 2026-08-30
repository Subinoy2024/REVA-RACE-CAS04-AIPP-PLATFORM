"""Platform-specific structural validator — checks required top-level keys."""

from __future__ import annotations

from typing import Tuple

import yaml

from backend.models.pipeline import CIPlatform


REQUIRED_KEYS = {
    CIPlatform.github_actions: {"name", "on", "jobs"},
    CIPlatform.azure_devops: {"stages"},
    CIPlatform.gitlab_ci: {"stages"},
    CIPlatform.harness: {"pipeline"},
    CIPlatform.tekton: {"apiVersion", "kind"},
}


class PlatformValidator:
    def check(self, platform: CIPlatform, content: str) -> Tuple[bool, str]:
        try:
            docs = [d for d in yaml.safe_load_all(content) if d]
        except yaml.YAMLError as e:
            return False, f"cannot parse YAML: {e}"
        required = REQUIRED_KEYS.get(platform, set())
        # For multi-doc YAML (Tekton) at least one doc must satisfy required keys
        for d in docs:
            if isinstance(d, dict) and required.issubset(d.keys()):
                return True, f"top-level keys present: {sorted(required)}"
        return False, f"missing required top-level keys for {platform.value}: {sorted(required)}"
