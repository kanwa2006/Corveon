"""MeSH connector (blueprint §8) — concept normalization against NLM's MeSH
lookup service. Confirms a term is a recognized, standardized medical
vocabulary entry (or finds the nearest one) rather than doing literature
search itself; PubMed is the literature-evidence connector."""

from __future__ import annotations

import httpx
from redis.asyncio import Redis

from app.data.models.evidence import EvidenceSourceName
from app.evidence.cache import UNAVAILABLE, Unavailable, get_or_fetch
from app.evidence.connectors.base import EvidenceResult
from app.providers.budget import TokenBucket


def _descriptor_id_from_resource(resource: str) -> str:
    return resource.rstrip("/").rsplit("/", 1)[-1]


class MeshConnector:
    name = EvidenceSourceName.MESH

    def __init__(
        self,
        *,
        base_url: str,
        redis: Redis,
        cache_ttl_seconds: int,
        max_rps: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._redis = redis
        self._cache_ttl_seconds = cache_ttl_seconds
        self._bucket = TokenBucket(capacity=max_rps, refill_rate_per_second=max_rps)
        self._transport = transport

    async def search(self, query: str, *, limit: int = 5) -> list[EvidenceResult]:
        async def fetch() -> list[dict[str, object]] | Unavailable:
            if not self._bucket.try_consume():
                return UNAVAILABLE
            try:
                return await self._fetch_from_api(query, limit)
            except (httpx.HTTPError, ValueError):
                # Transport-level failures (connection reset, timeout) and
                # unparseable bodies are the source being unreachable, not
                # the source answering — same UNAVAILABLE contract as an
                # HTTP 5xx: never cached, never raised out of search/lookup.
                return UNAVAILABLE

        cached = await get_or_fetch(
            self._redis,
            source=self.name.value,
            query=f"{query}:{limit}",
            ttl_seconds=self._cache_ttl_seconds,
            fetch=fetch,
        )
        return [EvidenceResult.from_cache_dict(row) for row in cached]

    async def _fetch_from_api(
        self, query: str, limit: int
    ) -> list[dict[str, object]] | Unavailable:
        async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
            response = await client.get(
                f"{self._base_url}/lookup/term",
                params={"label": query, "match": "contains", "limit": limit},
            )
        if response.status_code >= 400:
            return UNAVAILABLE

        entries = response.json()
        if not isinstance(entries, list):
            return []

        results: list[EvidenceResult] = []
        for entry in entries[:limit]:
            resource = entry.get("resource")
            label = entry.get("label")
            if not resource or not label:
                continue
            descriptor_id = _descriptor_id_from_resource(resource)
            results.append(
                EvidenceResult(
                    source=self.name,
                    title=label,
                    url=resource,
                    identifier=descriptor_id,
                    snippet=f"MeSH descriptor {descriptor_id}",
                    published_date=None,
                )
            )
        return [r.to_cache_dict() for r in results]
