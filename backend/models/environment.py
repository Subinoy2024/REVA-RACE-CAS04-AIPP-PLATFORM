"""Environment-deployment schemas."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class EnvironmentName(str, Enum):
    development = "development"
    qa = "qa"
    staging = "staging"
    production = "production"


class DeploymentStrategy(str, Enum):
    rolling = "rolling"
    blue_green = "blue_green"
    canary = "canary"
    recreate = "recreate"


# Known safe aliases from LLM outputs mapped to the strict enum
_TRIGGER_ALIASES = {
    "feature": "feature_branch",
    "feature/*": "feature_branch",
    "feature_branch": "feature_branch",
    "feature/*_branch": "feature_branch",
    "develop": "develop_branch",
    "develop_branch": "develop_branch",
    "release": "release_branch",
    "release/*": "release_branch",
    "release_branch": "release_branch",
    "release/*_branch": "release_branch",
    "main": "main_branch",
    "master": "main_branch",
    "main_branch": "main_branch",
    "tag": "version_tag",
    "v*.*.*": "version_tag",
    "version_tag": "version_tag",
    "manual": "manual",
    "manual_dispatch": "manual",
    "workflow_dispatch": "manual",
}

_STRATEGY_ALIASES = {
    "gated": "rolling",
    "approval": "rolling",
    "rolling_update": "rolling",
    "rolling": "rolling",
    "blue_green": "blue_green",
    "blue-green": "blue_green",
    "canary": "canary",
    "recreate": "recreate",
    "immutable": "recreate",
}


class EnvironmentRule(BaseModel):
    name: EnvironmentName
    trigger: Literal[
        "feature_branch", "develop_branch", "release_branch",
        "main_branch", "version_tag", "manual",
    ]
    branch_pattern: str = ""
    requires_approval: bool = False
    approvers: List[str] = Field(default_factory=list)
    deployment_strategy: DeploymentStrategy = DeploymentStrategy.rolling
    health_check: bool = True
    smoke_test: bool = True
    rollback: bool = True
    variables: List[str] = Field(default_factory=list)
    secrets: List[str] = Field(default_factory=list)
    explanation: str = ""

    @field_validator("trigger", mode="before")
    @classmethod
    def _coerce_trigger(cls, v: Any) -> str:
        if not isinstance(v, str):
            return v
        key = v.strip().lower()
        if key in _TRIGGER_ALIASES:
            return _TRIGGER_ALIASES[key]
        # Loose match: pick the trigger name that appears as a substring
        for alias, canonical in _TRIGGER_ALIASES.items():
            if alias in key:
                return canonical
        # Regex fallback for branch-like patterns
        if re.match(r"^v[\d.*]+", key):
            return "version_tag"
        return v

    @field_validator("deployment_strategy", mode="before")
    @classmethod
    def _coerce_strategy(cls, v: Any) -> str:
        if not isinstance(v, str):
            return v
        key = v.strip().lower().replace("-", "_")
        return _STRATEGY_ALIASES.get(key, v)


class EnvironmentPlan(BaseModel):
    rules: List[EnvironmentRule]
    summary: str = ""
