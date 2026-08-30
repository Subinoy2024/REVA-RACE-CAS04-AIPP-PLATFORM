"""n8n workflow schemas — used by the n8n status tab."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class N8nWorkflowStatus(BaseModel):
    id: str
    name: str
    active: bool
    trigger_type: Optional[str] = None
    environment: Optional[str] = None
    last_execution_status: Optional[str] = None
    last_execution_time: Optional[datetime] = None
    success: Optional[bool] = None
    tags: List[str] = Field(default_factory=list)


class N8nStatusResponse(BaseModel):
    configured: bool
    reason: Optional[str] = None
    workflows: List[N8nWorkflowStatus] = Field(default_factory=list)
