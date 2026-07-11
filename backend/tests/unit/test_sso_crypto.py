"""Unit tests for app/sso/crypto.py (ADR-0025)."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.sso.crypto import (
    SsoEncryptionNotConfiguredError,
    decrypt_client_secret,
    encrypt_client_secret,
)
from cryptography.fernet import Fernet

pytestmark = pytest.mark.unit


def _settings(**overrides: object) -> Settings:
    return Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        **overrides,  # type: ignore[arg-type]
    )


def _settings_without_env_file(**overrides: object) -> Settings:
    # Isolates from a local backend/.env that happens to have
    # SSO_CONFIG_ENCRYPTION_KEY set (e.g. from manual verification) — the
    # same isolation test_config.py's own "requires"/"unset" tests use.
    return Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        _env_file=None,  # type: ignore[call-arg]
        **overrides,  # type: ignore[arg-type]
    )


def test_encrypt_then_decrypt_round_trips() -> None:
    settings = _settings(SSO_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"))
    encrypted = encrypt_client_secret("super-secret-value", settings)
    assert encrypted != "super-secret-value"
    assert decrypt_client_secret(encrypted, settings) == "super-secret-value"


def test_encrypt_raises_when_key_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SSO_CONFIG_ENCRYPTION_KEY", raising=False)
    settings = _settings_without_env_file()
    with pytest.raises(SsoEncryptionNotConfiguredError, match="SSO_CONFIG_ENCRYPTION_KEY"):
        encrypt_client_secret("super-secret-value", settings)


def test_decrypt_raises_when_key_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SSO_CONFIG_ENCRYPTION_KEY", raising=False)
    settings = _settings_without_env_file()
    with pytest.raises(SsoEncryptionNotConfiguredError, match="SSO_CONFIG_ENCRYPTION_KEY"):
        decrypt_client_secret("anything", settings)


def test_decrypt_raises_when_key_has_changed() -> None:
    original = _settings(SSO_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"))
    encrypted = encrypt_client_secret("super-secret-value", original)

    different_key = _settings(SSO_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"))
    with pytest.raises(SsoEncryptionNotConfiguredError, match="could not be decrypted"):
        decrypt_client_secret(encrypted, different_key)
