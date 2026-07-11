"""RxNorm/RxNav connector (blueprint §8) — drug-name normalization, not DDI
lookup (the RxNav DDI API was discontinued 2024-01-02, ADR-0004). Uses
``/drugs.json``, which returns candidate RxCUIs *and* canonical names in one
call, rather than chaining an exact-match + approximate-match + per-result
property lookup across three separate requests."""

from __future__ import annotations

import httpx
from redis.asyncio import Redis

from app.data.models.evidence import EvidenceSourceName
from app.evidence.cache import UNAVAILABLE, Unavailable, get_or_fetch
from app.evidence.connectors.base import EvidenceResult
from app.providers.budget import TokenBucket


class RxNormConnector:
    name = EvidenceSourceName.RXNORM

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
        # Injectable only so tests can substitute httpx.MockTransport,
        # matching every provider adapter's own testability seam.
        self._transport = transport

    async def search(self, query: str, *, limit: int = 5) -> list[EvidenceResult]:
        async def fetch() -> list[dict[str, object]] | Unavailable:
            if not self._bucket.try_consume():
                return UNAVAILABLE
            return await self._fetch_from_api(query, limit)

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
            response = await client.get(f"{self._base_url}/drugs.json", params={"name": query})
        if response.status_code >= 400:
            return UNAVAILABLE

        data = response.json()
        concept_groups = data.get("drugGroup", {}).get("conceptGroup") or []
        results: list[EvidenceResult] = []
        for group in concept_groups:
            for prop in group.get("conceptProperties") or []:
                rxcui = prop.get("rxcui")
                concept_name = prop.get("name")
                if not rxcui or not concept_name:
                    continue
                results.append(
                    EvidenceResult(
                        source=self.name,
                        title=concept_name,
                        url=f"https://mor.nlm.nih.gov/RxNav/search?searchBy=RXCUI&searchTerm={rxcui}",
                        identifier=rxcui,
                        snippet=f"RxNorm concept unique identifier (RxCUI): {rxcui}",
                        published_date=None,
                    )
                )
                if len(results) >= limit:
                    return [r.to_cache_dict() for r in results]
        return [r.to_cache_dict() for r in results]
