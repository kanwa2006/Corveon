"""Unit tests: typed Settings (docs/ENVIRONMENT.md contract)."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from pydantic import ValidationError


@pytest.mark.unit
def test_settings_loads_required_fields() -> None:
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
    )
    assert settings.CORVEON_ENV == "development"
    assert settings.JWT_ACCESS_TTL_SECONDS == 900


@pytest.mark.unit
def test_settings_rejects_placeholder_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            JWT_SECRET_KEY="change-me-min-32-bytes-of-random",
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        )


@pytest.mark.unit
def test_settings_requires_database_url() -> None:
    with pytest.raises(ValidationError):
        Settings(JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value")  # type: ignore[call-arg]


@pytest.mark.unit
def test_provider_key_pool_parsing_is_empty_when_unset() -> None:
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
    )
    # Absent providers are a normal, valid state (ADR-0006) — never an error.
    assert settings.gemini_api_key_pool == []
    assert settings.anthropic_api_key_pool == []


@pytest.mark.unit
def test_provider_key_pool_parses_csv() -> None:
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        GEMINI_API_KEYS="key-one, key-two ,key-three",
    )
    assert settings.gemini_api_key_pool == ["key-one", "key-two", "key-three"]
