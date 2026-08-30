"""Agent skill contract.

Every agent in AIPP self-declares its capabilities via an `AgentSkill`
dataclass. This makes the agent system **introspectable** — any other
component (or LLM) can list agents, inspect their I/O contracts, and know
which MCP adapters they read from or write to without reading source code.

Design decision (see /app/docs/AGENT_REGISTRY.md):
  - We did NOT adopt the A2A (Agent-to-Agent) HTTP protocol because AIPP's
    agents run in one FastAPI process — a network hop would be wasted
    overhead. Instead, LangGraph's typed shared state is our transport, and
    `AgentSkill` is our equivalent of A2A's "agent card".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Type

from pydantic import BaseModel


@dataclass(frozen=True)
class AgentSkill:
    """Declarative contract for one agent.

    Attributes:
        name:            Stable identifier — used as the node name in
                         LangGraph and as the key in the registry.
        label:           Human-readable name shown in the UI.
        description:     One-sentence summary of what the agent does.
        skills:          Bullet-point capabilities (max 5).
        inputs:          Pydantic model the agent reads (from AIPPState).
                         `None` means it reads primitive state keys only.
        outputs:         Pydantic model the agent writes back to state.
        reads_mcp:       MCP adapter names this agent calls read-only.
        writes_mcp:      MCP adapter names this agent calls with writes.
        depends_on:      Names of agents whose output this agent consumes.
        llm_backed:      True if the agent calls the LLM (spends tokens).
    """

    name: str
    label: str
    description: str
    skills: List[str]
    outputs: Type[BaseModel]
    inputs: Optional[Type[BaseModel]] = None
    reads_mcp: List[str] = field(default_factory=list)
    writes_mcp: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    llm_backed: bool = True

    def to_card(self) -> dict:
        """Return a JSON-safe dict — the equivalent of an A2A agent card."""
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "skills": list(self.skills),
            "inputs": self.inputs.__name__ if self.inputs else None,
            "outputs": self.outputs.__name__,
            "reads_mcp": list(self.reads_mcp),
            "writes_mcp": list(self.writes_mcp),
            "depends_on": list(self.depends_on),
            "llm_backed": self.llm_backed,
        }
