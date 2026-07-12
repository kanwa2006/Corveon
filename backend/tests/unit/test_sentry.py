"""Unit tests for optional Sentry initialization (app/core/sentry.py, §16)."""

from __future__ import annotations

import pytest
import sentry_sdk
from app.core.sentry import configure_sentry

pytestmark = pytest.mark.unit


def test_configure_sentry_is_a_no_op_without_a_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))

    configure_sentry(None, "production")
    configure_sentry("", "production")

    assert calls == []


def test_configure_sentry_initializes_with_the_configured_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))

    configure_sentry("https://key@sentry.example/1", "production")

    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://key@sentry.example/1"
    assert calls[0]["environment"] == "production"
    # Clinical platform: never send PII by default.
    assert calls[0]["send_default_pii"] is False
