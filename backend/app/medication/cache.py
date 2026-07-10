"""Cache-first fetch helper for the Medication-Safety Engine's live lookups
(RxNorm normalization, openFDA DDI fallback) — same Redis-not-Postgres
pattern as the Evidence Verification Engine (ADR-0017), kept as a separate,
identically-shaped helper (rather than importing app.evidence.cache) so the
two domains don't couple to one shared module's evolution; the key prefix
also stays domain-scoped (``medication:...`` vs ``evidence:...``)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis


def _cache_key(source: str, query: str) -> str:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"medication:{source}:{digest}"


async def get_or_fetch(
    redis: Redis,
    *,
    source: str,
    query: str,
    ttl_seconds: int,
    fetch: Callable[[], Awaitable[dict[str, object] | None]],
) -> dict[str, object] | None:
    """Returns a cached result for ``query`` under ``source``, or calls
    ``fetch`` and caches the result (including a "no match" ``None``, so a
    genuinely unmatched drug name doesn't re-hit the API every time)."""
    key = _cache_key(source, query)
    cached = await redis.get(key)
    if cached is not None:
        cached_value: dict[str, object] | None = json.loads(cached)
        return cached_value

    fetched = await fetch()
    await redis.set(key, json.dumps(fetched), ex=ttl_seconds)
    return fetched
