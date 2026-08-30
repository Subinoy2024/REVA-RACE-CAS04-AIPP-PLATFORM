"""Validation report schema — output of the PipelineValidationAgent.

Kept intentionally small; agents currently emit a plain dict for backwards
compatibility, but this schema is the formal contract exposed via the
agent registry and via `/api/agents`.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ValidationCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class ValidationReport(BaseModel):
    passed: bool
    checks: List[ValidationCheck] = Field(default_factory=list)
