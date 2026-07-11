"""Cache-first fetch helper for OIDC discovery documents and JWKS
(ADR-0025) — same Redis-not-Postgres pattern as the Evidence Verification
Engine (ADR-0017) and the Medication-Safety Engine
(app/medication/cache.py), kept as a separate, identically-shaped helper
(rather than importing one of those) so the domains don't couple to one
shared module's evolution; the key prefix stays domain-scoped
(``sso:...``)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis


def _cache_key(source: str, query: str) -> str:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"sso:{source}:{digest}"


async def get_or_fetch(
    redis: Redis,
    *,
    source: str,
    query: str,
    ttl_seconds: int,
    fetch: Callable[[], Awaitable[dict[str, object] | None]],
) -> dict[str, object] | None:
    """Returns a cached result for ``query`` under ``source``, or calls
    ``fetch`` and caches the result. Unlike app/medication/cache.py, a
    ``None`` (fetch failure) is deliberately *not* cached — a transient
    discovery/JWKS outage shouldn't lock every login attempt out of the IdP
    for a full TTL; the next attempt just retries."""
    key = _cache_key(source, query)
    cached = await redis.get(key)
    if cached is not None:
        cached_value: dict[str, object] | None = json.loads(cached)
        return cached_value

    fetched = await fetch()
    if fetched is not None:
        await redis.set(key, json.dumps(fetched), ex=ttl_seconds)
    return fetched
