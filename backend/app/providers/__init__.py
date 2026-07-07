"""Provider-agnostic AI layer (§5, ADR-0006).

A registry of optional provider plugins discovered at boot, each implementing a
common ``generate()``/``embed()`` interface. Handles key-pool rotation, weighted
load balancing, ordered failover, circuit breaking, retries with jitter, token-
bucket rate limiting, and health monitoring. **Absence of a provider is normal,
not an error** — an unconfigured provider produces no warning/retry/health noise.
Zero providers reachable ⇒ degraded mode (deterministic features still work).
"""
