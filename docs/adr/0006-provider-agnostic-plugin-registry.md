# ADR-0006: Provider-agnostic plugin registry; absence ≠ failure

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
Corveon must not be locked to any AI vendor, must survive missing/quota-limited providers, and must
run for a solo dev on free tiers (Gemini free = 5–15 RPM). A hard requirement (§23.1): "if only one
provider exists, operate normally; missing providers must never generate warnings, failures,
retries, or errors."

## Decision
Treat every provider as an **optional plugin discovered at boot**, registered via config/env only
(`{name, adapter, base_url, model_ids, key_pool, priority, capabilities, rpm_limit, rpd_limit}`).
- **Zero providers configured is valid.** Implicit floor: Ollama-local when reachable. If no LLM
  provider is reachable, enter **degraded mode** — deterministic, non-LLM features still work fully;
  LLM-dependent steps return a typed `provider_unavailable` result rendered as an empty state.
- **Absence ≠ failure.** An unconfigured provider produces no warning, retry, health-check noise, or
  config error. Only *configured-but-unreachable* providers trigger health/failover logic.
- **Capability-based routing.** The router considers only registered ∧ healthy providers, ranked by
  priority; routing code never names a concrete provider.

## Consequences
- The platform is genuinely usable with one provider, many providers, or none.
- Business logic is provider-independent and testable with fakes.
- Throughput control (per-request LLM budget + shared token-bucket, §23.2) prevents multi-agent
  fan-out from self-throttling on free tiers.

## Alternatives considered
- **Single hardcoded provider:** simplest, but vendor lock-in and fragile under quota limits.
- **Framework-managed providers:** adds dependency churn and hides the failover logic we need to trace.
