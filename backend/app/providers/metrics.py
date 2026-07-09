"""Provider-call Prometheus metrics (docs/DEBUGGING.md §16). Kept in the
provider subsystem rather than app/core/metrics.py, per that module's own
note that per-provider metrics "land with those subsystems"."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

PROVIDER_CALLS = Counter(
    "corveon_provider_calls_total",
    "Total provider call attempts, by provider and outcome",
    # outcome: success | failure | skipped_circuit_open | skipped_rate_limited
    ["provider", "outcome"],
)
PROVIDER_CALL_LATENCY = Histogram(
    "corveon_provider_call_duration_seconds",
    "Provider call latency in seconds (successful calls only)",
    ["provider"],
)
