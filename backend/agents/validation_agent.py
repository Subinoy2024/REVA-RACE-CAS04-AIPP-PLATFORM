"""Pipeline Validation Agent — runs the deterministic validators
(yaml / platform-schema / security / environment-rule).
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.models.environment import EnvironmentPlan
from backend.models.pipeline import GeneratedPipeline
from backend.validators.environment_validator import EnvironmentValidator
from backend.validators.platform_validator import PlatformValidator
from backend.validators.security_validator import SecurityValidator
from backend.validators.yaml_validator import YAMLValidator


class PipelineValidationAgent:
    name = "pipeline_validation_agent"

    def run(self, *, pipeline: GeneratedPipeline, env_plan: EnvironmentPlan) -> Dict[str, Any]:
        checks: List[dict] = []
        yaml_ok, yaml_msg = YAMLValidator().check(pipeline.yaml_content)
        checks.append({"name": "yaml_syntax", "passed": yaml_ok, "detail": yaml_msg})

        plat_ok, plat_msg = PlatformValidator().check(
            pipeline.ci_platform, pipeline.yaml_content
        )
        checks.append({"name": "platform_schema", "passed": plat_ok, "detail": plat_msg})

        sec_ok, sec_msg = SecurityValidator().check(pipeline.yaml_content)
        checks.append({"name": "security_rules", "passed": sec_ok, "detail": sec_msg})

        env_ok, env_msg = EnvironmentValidator().check(env_plan)
        checks.append({"name": "environment_rules", "passed": env_ok, "detail": env_msg})

        all_ok = all(c["passed"] for c in checks)
        return {"passed": all_ok, "checks": checks}
