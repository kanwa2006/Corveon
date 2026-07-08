"""Unit tests for the provider circuit breaker (app/providers/health.py)."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from app.providers.health import CircuitBreaker, ProviderHealthTracker

pytestmark = pytest.mark.unit


def test_circuit_breaker_starts_closed() -> None:
    breaker = CircuitBreaker()
    assert breaker.is_open() is False
    assert breaker.consecutive_failures == 0


def test_circuit_breaker_opens_after_threshold_consecutive_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open() is False
    breaker.record_failure()
    assert breaker.is_open() is True


def test_circuit_breaker_success_resets_failure_count() -> None:
    breaker = CircuitBreaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    assert breaker.is_open() is False
    assert breaker.consecutive_failures == 1


def test_circuit_breaker_half_opens_after_cooldown() -> None:
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=10.0)
    breaker.record_failure()
    assert breaker.is_open() is True

    with patch("app.providers.health.time.monotonic", return_value=time.monotonic() + 11.0):
        assert breaker.is_open() is False


def test_circuit_breaker_reopens_if_half_open_probe_fails() -> None:
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=10.0)
    breaker.record_failure()
    with patch("app.providers.health.time.monotonic", return_value=time.monotonic() + 11.0):
        assert breaker.is_open() is False  # half-open probe allowed through
        breaker.record_failure()  # the probe itself failed
        assert breaker.is_open() is True


def test_circuit_breaker_closes_if_half_open_probe_succeeds() -> None:
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=10.0)
    breaker.record_failure()
    with patch("app.providers.health.time.monotonic", return_value=time.monotonic() + 11.0):
        assert breaker.is_open() is False
        breaker.record_success()
    assert breaker.is_open() is False
    assert breaker.consecutive_failures == 0


def test_provider_health_tracker_is_available_by_default_for_unknown_provider() -> None:
    tracker = ProviderHealthTracker()
    assert tracker.is_available("never-seen-before") is True


def test_provider_health_tracker_tracks_providers_independently() -> None:
    tracker = ProviderHealthTracker(failure_threshold=1)
    tracker.record_failure("gemini")
    assert tracker.is_available("gemini") is False
    assert tracker.is_available("ollama") is True


def test_provider_health_tracker_snapshot_reports_tracked_providers_only() -> None:
    tracker = ProviderHealthTracker(failure_threshold=1)
    tracker.record_failure("gemini")
    snapshot = tracker.snapshot()
    assert snapshot == {"gemini": {"circuit_open": True, "consecutive_failures": 1}}
