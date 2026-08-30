"""PipelineDoctor RCA schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class LogEvidence(BaseModel):
    line_range: str = ""              # e.g. "L120-L128"
    snippet: str
    interpretation: str = ""


class RCAReport(BaseModel):
    ci_platform: str
    failed_stage: Optional[str] = None
    root_cause: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence: List[LogEvidence] = Field(default_factory=list)
    ai_inferences: List[str] = Field(default_factory=list)
    corrective_actions: List[str] = Field(default_factory=list)
    preventive_actions: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    disclaimer: str = (
        "Evidence items are lifted verbatim from the log; inferences are model-generated interpretations."
    )
