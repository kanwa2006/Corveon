"""DailyMed connector (blueprint §8) — authoritative structured product
label (SPL) text, straight from the FDA's own label repository."""

from __future__ import annotations

from datetime import date

import httpx
from redis.asyncio import Redis

from app.data.models.evidence import EvidenceSourceName
from app.evidence.cache import get_or_fetch
from app.evidence.connectors.base import EvidenceResult
from app.providers.budget import TokenBucket


def _parse_published_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


class DailyMedConnector:
    name = EvidenceSourceName.DAILYMED

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
        async def fetch() -> list[dict[str, object]]:
            if not self._bucket.try_consume():
                return []
            return await self._fetch_from_api(query, limit)

        cached = await get_or_fetch(
            self._redis,
            source=self.name.value,
            query=f"{query}:{limit}",
            ttl_seconds=self._cache_ttl_seconds,
            fetch=fetch,
        )
        return [EvidenceResult.from_cache_dict(row) for row in cached]

    async def _fetch_from_api(self, query: str, limit: int) -> list[dict[str, object]]:
        async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
            response = await client.get(
                f"{self._base_url}/spls.json", params={"drug_name": query, "pagesize": limit}
            )
        if response.status_code >= 400:
            return []

        data = response.json()
        results: list[EvidenceResult] = []
        for record in (data.get("data") or [])[:limit]:
            setid = record.get("setid")
            title = record.get("title")
            if not setid or not title:
                continue
            results.append(
                EvidenceResult(
                    source=self.name,
                    title=title,
                    url=f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}",
                    identifier=setid,
                    # DailyMed's search endpoint returns SPL metadata only —
                    # the full label text needs a separate per-SPL fetch this
                    # connector doesn't make (out of scope: the title itself,
                    # from the FDA-approved label, is already a real,
                    # resolvable piece of evidence without it).
                    snippet=None,
                    published_date=_parse_published_date(record.get("published_date")),
                )
            )
        return [r.to_cache_dict() for r in results]
