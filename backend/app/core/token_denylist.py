"""Refresh-token revocation via a Redis denylist.

JWTs are stateless, so logout must explicitly record that a refresh token's
``jti`` is no longer honored. The denylist entry TTLs out at the token's own
expiry — no unbounded growth, no manual cleanup job needed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from redis.asyncio import Redis

_KEY_PREFIX = "corveon:revoked-jti:"


def _key(jti: str) -> str:
    return f"{_KEY_PREFIX}{jti}"


async def revoke(redis: Redis, jti: str, expires_at: datetime) -> None:
    ttl_seconds = max(1, int((expires_at - datetime.now(UTC)).total_seconds()))
    await redis.set(_key(jti), "1", ex=ttl_seconds)


async def is_revoked(redis: Redis, jti: str) -> bool:
    return bool(await redis.exists(_key(jti)))
