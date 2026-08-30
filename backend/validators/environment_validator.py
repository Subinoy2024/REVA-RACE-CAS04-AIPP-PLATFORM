"""Environment-rule validator — ensures the 4 expected envs are covered and
production has approval enabled.
"""

from __future__ import annotations

from typing import Tuple

from backend.models.environment import EnvironmentName, EnvironmentPlan


class EnvironmentValidator:
    def check(self, env_plan: EnvironmentPlan) -> Tuple[bool, str]:
        names = {r.name for r in env_plan.rules}
        expected = {EnvironmentName.development, EnvironmentName.qa, EnvironmentName.staging, EnvironmentName.production}
        missing = expected - names
        if missing:
            return False, f"missing environment rules for: {[n.value for n in missing]}"
        prod = next((r for r in env_plan.rules if r.name == EnvironmentName.production), None)
        if prod and not prod.requires_approval:
            return False, "production must require manual approval"
        return True, "all 4 environments covered and production approval configured"
