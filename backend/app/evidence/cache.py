"""Cache-first fetch helper for evidence connectors (ADR-0017: Redis, not a
Postgres table). Keyed ``evidence:{source}:{sha256(query)}`` (blueprint
§10.4's ``{source}:{query_hash}`` convention) so the same query never re-hits
an external API within its TTL, regardless of which chat/user asked it —
this cache is not per-chat data and carries no per-chat isolation concern
(CLAUDE.md §3's isolation invariant governs chat *content*, not the shared
fact that "PubMed query X returned Y" independent of who asked)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Final, final

from redis.asyncio import Redis


@final
class Unavailable:
    """Sentinel a ``fetch`` returns when it couldn't ask the source at all
    (rate-limit bucket empty, HTTP error) — distinct from the source
    answering "nothing found". Never cached: caching it would turn a
    transient outage into a durable empty result for the full TTL."""


UNAVAILABLE: Final[Unavailable] = Unavailable()


def _cache_key(source: str, query: str) -> str:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"evidence:{source}:{digest}"


async def get_or_fetch(
    redis: Redis,
    *,
    source: str,
    query: str,
    ttl_seconds: int,
    fetch: Callable[[], Awaitable[list[dict[str, object]] | Unavailable]],
) -> list[dict[str, object]]:
    """Returns cached connector results for ``query`` under ``source``, or
    calls ``fetch`` and caches the result. Results are cached as plain JSON
    dicts (not connector-specific dataclasses) so this module has no
    dependency on any one connector's result type. A fetch that returns
    ``UNAVAILABLE`` yields ``[]`` for this call only — nothing is cached,
    so the next call retries the source."""
    key = _cache_key(source, query)
    cached = await redis.get(key)
    if cached is not None:
        result: list[dict[str, object]] = json.loads(cached)
        return result

    fetched = await fetch()
    if isinstance(fetched, Unavailable):
        return []
    await redis.set(key, json.dumps(fetched), ex=ttl_seconds)
    return fetched
