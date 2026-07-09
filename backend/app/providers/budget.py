"""Per-request LLM call budget and a shared token-bucket rate limiter
(CLAUDE.md §23.2). Two distinct mechanisms:

- ``LLMCallBudget`` caps how many LLM calls a *single* orchestrator request
  may make in total, across every provider/agent step it fans out to.
  Prevents one request's multi-agent work from silently making an unbounded
  number of calls. One instance is created per request and used only within
  that request's own coroutine — never shared across requests.
- ``TokenBucket`` is a *process-wide, per-provider* rate limiter tuned to
  that provider's published RPM limit (e.g. Gemini's free tier), shared
  across every request so concurrent requests collectively respect the
  limit rather than each getting their own private allowance.
"""

from __future__ import annotations

import time


class LLMCallBudgetExceededError(Exception):
    """Raised when a single request's LLM-call budget is exhausted."""


class LLMCallBudget:
    def __init__(self, max_calls: int) -> None:
        self._max_calls = max_calls
        self._calls_made = 0

    def consume(self) -> None:
        if self._calls_made >= self._max_calls:
            raise LLMCallBudgetExceededError(
                f"This request already made {self._calls_made} LLM call(s), "
                f"at its budget of {self._max_calls}."
            )
        self._calls_made += 1

    @property
    def calls_made(self) -> int:
        return self._calls_made


class TokenBucket:
    """Classic token bucket: refills continuously at
    ``refill_rate_per_second``, capped at ``capacity``. ``try_consume`` is
    non-blocking — a caller that finds the bucket empty should treat that
    provider as unavailable *right now* and fail over, not wait, matching
    every other provider-unavailable path (registry.py)."""

    def __init__(self, *, capacity: float, refill_rate_per_second: float) -> None:
        self._capacity = capacity
        self._refill_rate = refill_rate_per_second
        self._tokens = capacity
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def try_consume(self, tokens: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False
