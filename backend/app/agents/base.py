"""Common Agent protocol (blueprint §7): every agent is a single-responsibility
async step over the shared ``OrchestratorState``. A future agent (Evidence
Verification, Medication-Safety Analysis, Citation Verification, ... — Month
3+, once their subsystems exist) becomes one more file here implementing this
same protocol; the orchestrator gains a call to it, never a rewrite of the
agents already wired in."""

from __future__ import annotations

from typing import Protocol

from app.agents.state import OrchestratorState


class Agent(Protocol):
    name: str

    async def run(self, state: OrchestratorState) -> OrchestratorState: ...
