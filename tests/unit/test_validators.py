"""Unit tests for validators — pure Python, no network / no LLM."""

from __future__ import annotations

import pytest
import yaml

from backend.models.environment import (
    DeploymentStrategy,
    EnvironmentName,
    EnvironmentPlan,
    EnvironmentRule,
)
from backend.models.pipeline import CIPlatform
from backend.validators.environment_validator import EnvironmentValidator
from backend.validators.platform_validator import PlatformValidator
from backend.validators.security_validator import SecurityValidator
from backend.validators.yaml_validator import YAMLValidator


def test_yaml_validator_ok():
    ok, msg = YAMLValidator().check("a: 1\nb: [1, 2]\n")
    assert ok, msg


def test_yaml_validator_bad():
    ok, _ = YAMLValidator().check("a: [1, 2\n")
    assert not ok


def test_platform_validator_gh():
    yml = yaml.safe_dump({"name": "x", "on": {"push": {}}, "jobs": {"build": {"runs-on": "ubuntu-latest"}}})
    ok, msg = PlatformValidator().check(CIPlatform.github_actions, yml)
    assert ok, msg


def test_platform_validator_missing_keys():
    yml = yaml.safe_dump({"name": "x"})
    ok, _ = PlatformValidator().check(CIPlatform.github_actions, yml)
    assert not ok


def test_security_validator_hardcoded_pat():
    yml = "steps:\n  - run: echo ghp_abcdefghij0123456789ABCDEFGHIJ0123456789\n"
    ok, msg = SecurityValidator().check(yml)
    assert not ok
    assert "PAT" in msg


def test_security_validator_curl_pipe_sh():
    ok, _ = SecurityValidator().check("run: curl https://x/install | sh")
    assert not ok


def test_environment_validator_ok():
    plan = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch",
                        deployment_strategy=DeploymentStrategy.rolling, requires_approval=False),
        EnvironmentRule(name=EnvironmentName.qa, trigger="release_branch",
                        deployment_strategy=DeploymentStrategy.rolling, requires_approval=False),
        EnvironmentRule(name=EnvironmentName.staging, trigger="main_branch",
                        deployment_strategy=DeploymentStrategy.blue_green, requires_approval=True),
        EnvironmentRule(name=EnvironmentName.production, trigger="version_tag",
                        deployment_strategy=DeploymentStrategy.blue_green, requires_approval=True),
    ])
    ok, msg = EnvironmentValidator().check(plan)
    assert ok, msg


def test_environment_validator_production_needs_approval():
    plan = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch"),
        EnvironmentRule(name=EnvironmentName.qa, trigger="release_branch"),
        EnvironmentRule(name=EnvironmentName.staging, trigger="main_branch", requires_approval=True),
        EnvironmentRule(name=EnvironmentName.production, trigger="version_tag", requires_approval=False),
    ])
    ok, _ = EnvironmentValidator().check(plan)
    assert not ok


def test_environment_validator_missing_env():
    plan = EnvironmentPlan(rules=[
        EnvironmentRule(name=EnvironmentName.development, trigger="develop_branch"),
    ])
    ok, msg = EnvironmentValidator().check(plan)
    assert not ok
    assert "qa" in msg
