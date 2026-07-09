"""Unit tests for the per-request LLM call budget and shared token bucket
(app/providers/budget.py)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.providers.budget import LLMCallBudget, LLMCallBudgetExceededError, TokenBucket

pytestmark = pytest.mark.unit


def test_llm_call_budget_allows_calls_up_to_the_limit() -> None:
    budget = LLMCallBudget(max_calls=2)
    budget.consume()
    budget.consume()
    assert budget.calls_made == 2


def test_llm_call_budget_raises_once_exhausted() -> None:
    budget = LLMCallBudget(max_calls=1)
    budget.consume()
    with pytest.raises(LLMCallBudgetExceededError):
        budget.consume()


def test_llm_call_budget_of_zero_rejects_the_first_call() -> None:
    budget = LLMCallBudget(max_calls=0)
    with pytest.raises(LLMCallBudgetExceededError):
        budget.consume()


def test_token_bucket_allows_consumption_up_to_capacity() -> None:
    bucket = TokenBucket(capacity=2, refill_rate_per_second=0)
    assert bucket.try_consume() is True
    assert bucket.try_consume() is True
    assert bucket.try_consume() is False


def test_token_bucket_refills_over_time() -> None:
    with patch("app.providers.budget.time.monotonic", return_value=1000.0):
        bucket = TokenBucket(capacity=1, refill_rate_per_second=1.0)
        assert bucket.try_consume() is True
        assert bucket.try_consume() is False

    with patch("app.providers.budget.time.monotonic", return_value=1001.0):
        assert bucket.try_consume() is True


def test_token_bucket_never_exceeds_capacity() -> None:
    with patch("app.providers.budget.time.monotonic", return_value=1000.0):
        bucket = TokenBucket(capacity=1, refill_rate_per_second=1.0)
        bucket.try_consume()

    with patch("app.providers.budget.time.monotonic", return_value=1100.0):
        # 100 seconds elapsed at 1/s would refill to 100 tokens if uncapped —
        # capacity must clamp it to 1.
        assert bucket.try_consume(tokens=1.0) is True
        assert bucket.try_consume(tokens=0.01) is False
