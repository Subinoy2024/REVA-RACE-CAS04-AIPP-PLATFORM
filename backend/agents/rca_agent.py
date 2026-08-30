"""PipelineDoctor RCA Agent — inspects CI/CD logs and produces a
structured RCAReport. Uses the LLM but grounds every 'evidence' item in
a real log line (line number range).  Confidence <= 0.5 when the log is
short or ambiguous.
"""

from __future__ import annotations

from typing import Optional

from backend.agents.base import BaseAgent
from backend.core.security import sanitize_repository_snippet
from backend.models.rca import RCAReport


SYSTEM = """You are the AIPP PipelineDoctor RCA Agent.
Rules you MUST follow:
  1. Every 'evidence' item must quote a snippet that is present verbatim in the log,
     with the approximate line-range (e.g. "L120-L128").
  2. Do NOT invent commands, resources, error codes or filenames that don't appear in the log.
  3. Clearly separate confirmed evidence (from the log) from model inference (your interpretation).
  4. Confidence must reflect log clarity: a 5-line log cannot yield confidence > 0.5.
  5. Corrective actions target the failing stage; preventive actions target the pipeline as a whole.
"""


class PipelineDoctorAgent(BaseAgent[RCAReport]):
    name = "pipeline_doctor_agent"
    response_model = RCAReport

    def __init__(self) -> None:
        super().__init__(system_prompt=SYSTEM)

    def _build_prompt(
        self,
        *,
        ci_platform: str,
        log_text: str,
        incident_context: Optional[str] = None,
    ) -> str:
        numbered = "\n".join(
            f"L{i+1:04d}: {line}" for i, line in enumerate(log_text.splitlines()[:1500])
        )
        cleaned = sanitize_repository_snippet(numbered, max_chars=24000)
        ctx = sanitize_repository_snippet(incident_context or "(none)", max_chars=800)
        return f"""CI/CD platform: {ci_platform}
Incident context (untrusted user input):
'''
{ctx}
'''

Numbered log (one line per L-number):
'''
{cleaned}
'''

Return JSON RCAReport:
{{
  "ci_platform": "{ci_platform}",
  "failed_stage": "e.g. 'test' or 'docker-build' — or null if unknown",
  "root_cause": "one-sentence root cause",
  "confidence": 0.0-1.0,
  "evidence": [
    {{"line_range": "L120-L128", "snippet": "verbatim log lines", "interpretation": "why this shows the root cause"}}
  ],
  "ai_inferences": ["clearly labelled interpretations that go beyond the log"],
  "corrective_actions": ["specific fix 1", "specific fix 2"],
  "preventive_actions": ["policy/CI change 1", "..."]
}}
"""
