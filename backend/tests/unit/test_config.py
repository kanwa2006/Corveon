"""Unit tests: typed Settings (docs/ENVIRONMENT.md contract)."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from pydantic import ValidationError


@pytest.mark.unit
def test_settings_loads_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate from BOTH the ambient environment (CI sets CORVEON_ENV=test at
    # the job level) AND a local backend/.env file, either of which would
    # otherwise be picked up over the class default, making this assertion
    # environment-dependent.
    monkeypatch.delenv("CORVEON_ENV", raising=False)
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        _env_file=None,  # type: ignore[call-arg]
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
def test_settings_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate from BOTH the ambient environment (CI sets DATABASE_URL at the
    # job level) AND a local backend/.env file (any developer following
    # docs/SETUP.md's `cp .env.example .env` has one) — either would
    # otherwise satisfy this "required" field even though none was passed
    # explicitly here. _env_file=None skips dotenv loading for this instance
    # only; monkeypatch still covers the env-var layer.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(
            JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
            _env_file=None,  # type: ignore[call-arg]
        )


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


@pytest.mark.unit
def test_settings_defaults_to_pgvector() -> None:
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
    )
    # ADR-0001/ADR-0022: pgvector is the default, no config required for it.
    assert settings.VECTOR_STORE == "pgvector"


@pytest.mark.unit
def test_settings_rejects_qdrant_vector_store_without_a_url() -> None:
    with pytest.raises(ValidationError, match="QDRANT_URL is required"):
        Settings(
            JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
            VECTOR_STORE="qdrant",
        )


@pytest.mark.unit
def test_settings_accepts_qdrant_vector_store_with_a_url() -> None:
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        VECTOR_STORE="qdrant",
        QDRANT_URL="http://localhost:6333",
    )
    assert settings.VECTOR_STORE == "qdrant"
    assert settings.QDRANT_URL == "http://localhost:6333"


@pytest.mark.unit
def test_settings_has_no_read_replica_by_default() -> None:
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
    )
    # ADR-0023: unset is a normal, valid state — reads fall back to the primary.
    assert settings.DATABASE_READ_REPLICA_URL is None


@pytest.mark.unit
def test_settings_accepts_a_read_replica_url() -> None:
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        DATABASE_READ_REPLICA_URL="postgresql+asyncpg://user:pass@replica-host/db",
    )
    assert settings.DATABASE_READ_REPLICA_URL == "postgresql+asyncpg://user:pass@replica-host/db"


@pytest.mark.unit
def test_settings_defaults_to_standard_deployment_mode() -> None:
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
    )
    assert settings.DEPLOYMENT_MODE == "standard"
    assert settings.is_ollama_only is False


@pytest.mark.unit
def test_settings_accepts_ollama_only_deployment_mode() -> None:
    settings = Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        DEPLOYMENT_MODE="ollama_only",
    )
    assert settings.is_ollama_only is True
