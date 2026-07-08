"""ARQ (Redis queue) pool factory (ADR-0011) — shared by the API process (to
enqueue jobs) and the worker process (to run them). The same Redis serves
cache, token-denylist, and queue (ADR-0011)."""

from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import Settings


def redis_settings_from_url(url: str) -> RedisSettings:
    return RedisSettings.from_dsn(url)


async def create_arq_pool(settings: Settings) -> ArqRedis:
    return await create_pool(redis_settings_from_url(settings.REDIS_URL))
