"""Redis connection factory — shared by caching, the ARQ queue, and the token
denylist. A single Redis (Upstash in production) serves all three (ADR-0011)."""

from __future__ import annotations

from typing import cast

from redis.asyncio import Redis

from app.core.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return cast(Redis, Redis.from_url(settings.REDIS_URL, decode_responses=True))
