"""Orchestrator — custom, lightweight, typed async state graph (ADR-0003).

Owns the deterministic routing policy (§6): decides per request which agents,
retrieval strategies, and providers run, and — crucially — when NOT to retrieve
or NOT to invoke the agent graph (fast-path, §23.5). Enforces the per-request
LLM-call budget (§23.2). Emits a transparent ``routing_trace`` on every response.
Routing code never names a concrete provider.
"""
