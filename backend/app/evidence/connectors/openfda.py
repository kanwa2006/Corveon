"""openFDA connector (blueprint §8) — drug label evidence (approved
indications, warnings). Not the DDI fallback role blueprint §9 also
mentions for openFDA — that belongs to the Medication-Safety Engine (Month
6-12), out of this phase's scope."""

from __future__ import annotations

from datetime import date

import httpx
from redis.asyncio import Redis

from app.data.models.evidence import EvidenceSourceName
from app.evidence.cache import get_or_fetch
from app.evidence.connectors.base import EvidenceResult
from app.providers.budget import TokenBucket

_MAX_SNIPPET_CHARS = 500


def _parse_effective_time(raw: str | None) -> date | None:
    # openFDA's effective_time is YYYYMMDD, no separators.
    if not raw or len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


class OpenFdaConnector:
    name = EvidenceSourceName.OPENFDA

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        redis: Redis,
        cache_ttl_seconds: int,
        max_rpm: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._redis = redis
        self._cache_ttl_seconds = cache_ttl_seconds
        self._bucket = TokenBucket(capacity=max_rpm, refill_rate_per_second=max_rpm / 60)
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
        escaped = query.replace('"', '\\"')
        params: dict[str, str | int] = {
            "search": f'openfda.generic_name:"{escaped}" openfda.brand_name:"{escaped}"',
            "limit": limit,
        }
        if self._api_key:
            params["api_key"] = self._api_key

        async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
            response = await client.get(f"{self._base_url}/drug/label.json", params=params)
        if response.status_code >= 400:
            # openFDA returns 404 for a zero-result search, not an error
            # payload — the same as "nothing found," never a real failure.
            return []

        data = response.json()
        results: list[EvidenceResult] = []
        for record in data.get("results") or []:
            openfda_meta = record.get("openfda") or {}
            names = openfda_meta.get("brand_name") or openfda_meta.get("generic_name") or []
            title = names[0] if names else query
            indications = record.get("indications_and_usage") or []
            snippet = indications[0][:_MAX_SNIPPET_CHARS] if indications else None
            label_id = record.get("id")
            results.append(
                EvidenceResult(
                    source=self.name,
                    title=title,
                    # openFDA sources its label data from DailyMed SPLs; the
                    # record `id` is that SPL's DailyMed set id, giving a
                    # real, resolvable public page rather than no link at all.
                    url=(
                        f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={label_id}"
                        if label_id
                        else None
                    ),
                    identifier=label_id,
                    snippet=snippet,
                    published_date=_parse_effective_time(record.get("effective_time")),
                )
            )
        return [r.to_cache_dict() for r in results]
