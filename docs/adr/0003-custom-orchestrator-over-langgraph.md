# ADR-0003: Custom typed orchestrator over a heavyweight agent framework

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
The orchestrator routes each request to agents/retrieval/providers and must be fully observable and
testable. A solo developer will maintain this for years. The agent-framework ecosystem shipped more
breaking change in Q2 2026 than any prior quarter.

## Decision
Build a **custom, lightweight, typed orchestrator** — a plain Python async state-graph of nodes over
a Pydantic state object. Agents implement `run(state) -> state` and self-register. Keep a clean seam
so **LangGraph** can be adopted later for one specific complex flow without rewriting agents.

## Consequences
- Full control of tracing, deterministic routing, and testability; zero framework-upgrade risk.
- No opaque framework internals to debug; the routing policy is explicit and unit-testable.
- Tradeoff: we implement durable-state/HITL primitives ourselves if/when needed — mitigated by the
  LangGraph escape hatch for a single flow.

## Alternatives considered
- **LangGraph 1.0:** strongest production graph framework; designated fallback, but adds lock-in and
  churn risk for a solo dev now.
- **CrewAI / LlamaIndex Workflows / AutoGen / Pydantic-AI:** each optimizes for a niche (role
  prototypes, retrieval-first, enterprise/.NET, young) that doesn't fit the long-term solo path.
