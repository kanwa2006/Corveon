"""Provider health tracking + circuit breaker (docs/ARCHITECTURE.md §5,
CLAUDE.md §23.1).

Only ever tracks providers already present in the registry — a provider that
was never configured never appears here at all, consistent with "absence of
a provider is never an error" (ADR-0006). Health state is purely reactive: it
records the outcome of real calls the registry already made; there is no
background poller, which keeps this dependency-free and correct across
process restarts without extra infrastructure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class CircuitBreaker:
    """Per-provider circuit breaker. Opens after ``failure_threshold``
    consecutive failures and stays open for ``cooldown_seconds``, after which
    the next call is treated as a half-open probe: callers may attempt it,
    and its outcome (``record_success``/``record_failure``) decides whether
    the circuit closes again or re-opens. This is a deliberately simple
    single-process half-open model (it does not gate to exactly one
    concurrent probe) — adequate for this codebase's per-request sequential
    provider iteration; revisit only if concurrent load ever makes that
    imprecision matter.
    """

    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold and self._opened_at is None:
            self._opened_at = time.monotonic()

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at < self.cooldown_seconds:
            return True
        # Cooldown elapsed: allow a half-open probe through. If it fails,
        # record_failure() re-opens the clock; if it succeeds,
        # record_success() clears the breaker entirely.
        self._opened_at = None
        self._consecutive_failures = self.failure_threshold - 1
        return False

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures


class ProviderHealthTracker:
    """One CircuitBreaker per provider name, created lazily on first use so
    callers never need to pre-register providers."""

    def __init__(self, *, failure_threshold: int = 3, cooldown_seconds: float = 30.0) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._breakers: dict[str, CircuitBreaker] = {}

    def _breaker(self, provider: str) -> CircuitBreaker:
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(
                failure_threshold=self._failure_threshold,
                cooldown_seconds=self._cooldown_seconds,
            )
        return self._breakers[provider]

    def is_available(self, provider: str) -> bool:
        """False only while that provider's circuit is open (recent,
        repeated failures) — never for a provider that simply isn't
        configured, since those never appear in the registry's provider map
        to begin with (capability-based routing: the registry only ever
        considers registered-and-healthy providers, CLAUDE.md §23.1)."""
        return not self._breaker(provider).is_open()

    def record_success(self, provider: str) -> None:
        self._breaker(provider).record_success()

    def record_failure(self, provider: str) -> None:
        self._breaker(provider).record_failure()

    def snapshot(self) -> dict[str, dict[str, object]]:
        """A small serializable status report per tracked provider, for
        observability (logs / a future health endpoint) — not used for
        routing itself, which goes through ``is_available``."""
        return {
            name: {
                "circuit_open": breaker.is_open(),
                "consecutive_failures": breaker.consecutive_failures,
            }
            for name, breaker in self._breakers.items()
        }
