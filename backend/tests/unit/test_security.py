"""Unit tests: password hashing and JWT access/refresh tokens."""

from __future__ import annotations

import time

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        JWT_SECRET_KEY="unit-test-secret-not-for-production-use-32-bytes",
        DATABASE_URL="postgresql+asyncpg://unused:unused@localhost/unused",
        JWT_ACCESS_TTL_SECONDS=2,
        JWT_REFRESH_TTL_SECONDS=3600,
    )


@pytest.mark.unit
def test_password_hash_roundtrip(settings: Settings) -> None:
    hashed = hash_password("correct horse battery staple", settings)
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed, settings)


@pytest.mark.unit
def test_password_hash_rejects_wrong_password(settings: Settings) -> None:
    hashed = hash_password("correct horse battery staple", settings)
    assert not verify_password("wrong password", hashed, settings)


@pytest.mark.unit
def test_access_token_roundtrip(settings: Settings) -> None:
    token = create_access_token("user-123", settings, role="user")
    payload = decode_token(token, TokenType.ACCESS, settings)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert payload["role"] == "user"


@pytest.mark.unit
def test_refresh_token_roundtrip(settings: Settings) -> None:
    token = create_refresh_token("user-123", settings)
    payload = decode_token(token, TokenType.REFRESH, settings)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


@pytest.mark.unit
def test_decode_rejects_wrong_token_type(settings: Settings) -> None:
    access = create_access_token("user-123", settings)
    with pytest.raises(InvalidTokenError):
        decode_token(access, TokenType.REFRESH, settings)


@pytest.mark.unit
def test_decode_rejects_expired_token(settings: Settings) -> None:
    token = create_access_token("user-123", settings)
    time.sleep(2.1)  # settings.JWT_ACCESS_TTL_SECONDS == 2
    with pytest.raises(InvalidTokenError):
        decode_token(token, TokenType.ACCESS, settings)


@pytest.mark.unit
def test_decode_rejects_tampered_signature(settings: Settings) -> None:
    token = create_access_token("user-123", settings)
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(InvalidTokenError):
        decode_token(tampered, TokenType.ACCESS, settings)


@pytest.mark.unit
def test_decode_rejects_token_signed_with_different_secret(settings: Settings) -> None:
    other_secret_token = jwt.encode(
        {"sub": "user-123", "type": "access"}, "a-completely-different-secret", algorithm="HS256"
    )
    with pytest.raises(InvalidTokenError):
        decode_token(other_secret_token, TokenType.ACCESS, settings)
