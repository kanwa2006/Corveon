"""Password hashing (Argon2id) and JWT access/refresh tokens.

CLAUDE.md §8: secrets via env only. Access tokens are short-lived and carry no
revocation state; refresh tokens carry a ``jti`` that the denylist (see
app/core/token_denylist.py) can revoke on logout.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import Settings


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(Exception):
    """Raised when a JWT is malformed, expired, or the wrong type."""


def _hasher(settings: Settings) -> PasswordHasher:
    return PasswordHasher(
        time_cost=settings.ARGON2_TIME_COST,
        memory_cost=settings.ARGON2_MEMORY_COST,
        parallelism=settings.ARGON2_PARALLELISM,
    )


def hash_password(password: str, settings: Settings) -> str:
    return _hasher(settings).hash(password)


def verify_password(password: str, password_hash: str, settings: Settings) -> bool:
    try:
        return _hasher(settings).verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _encode(
    *,
    subject: str,
    token_type: TokenType,
    ttl_seconds: int,
    settings: Settings,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def create_access_token(user_id: str, settings: Settings, *, role: str | None = None) -> str:
    extra = {"role": role} if role is not None else None
    return _encode(
        subject=user_id,
        token_type=TokenType.ACCESS,
        ttl_seconds=settings.JWT_ACCESS_TTL_SECONDS,
        settings=settings,
        extra_claims=extra,
    )


def create_refresh_token(user_id: str, settings: Settings) -> str:
    return _encode(
        subject=user_id,
        token_type=TokenType.REFRESH,
        ttl_seconds=settings.JWT_REFRESH_TTL_SECONDS,
        settings=settings,
    )


def decode_token(token: str, expected_type: TokenType, settings: Settings) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(
            f"expected a {expected_type.value} token, got {payload.get('type')!r}"
        )
    return payload
