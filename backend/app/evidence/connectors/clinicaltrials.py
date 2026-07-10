"""ClinicalTrials.gov connector (blueprint §8) — trial evidence via the v2
studies API. One call returns matching studies with title, id, and summary
together, unlike PubMed's two-step esearch/esummary."""

from __future__ import annotations

import re
from datetime import date

import httpx
from redis.asyncio import Redis

from app.data.models.evidence import EvidenceSourceName
from app.evidence.cache import get_or_fetch
from app.evidence.connectors.base import EvidenceResult
from app.providers.budget import TokenBucket

_MAX_SNIPPET_CHARS = 500


def _parse_study_date(raw: str | None) -> date | None:
    """ClinicalTrials.gov dates are "YYYY-MM-DD", "YYYY-MM", or "YYYY" —
    same honest partial-date handling as the PubMed connector's pubdate."""
    if not raw:
        return None
    match = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", raw.strip())
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else 1
    day = int(match.group(3)) if match.group(3) else 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


class ClinicalTrialsConnector:
    name = EvidenceSourceName.CLINICALTRIALS

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
                f"{self._base_url}/studies", params={"query.term": query, "pageSize": limit}
            )
        if response.status_code >= 400:
            return []

        data = response.json()
        results: list[EvidenceResult] = []
        for study in (data.get("studies") or [])[:limit]:
            protocol = study.get("protocolSection") or {}
            identification = protocol.get("identificationModule") or {}
            nct_id = identification.get("nctId")
            title = identification.get("briefTitle")
            if not nct_id or not title:
                continue
            description = protocol.get("descriptionModule") or {}
            summary = description.get("briefSummary")
            status_module = protocol.get("statusModule") or {}
            start_date = (status_module.get("startDateStruct") or {}).get("date")
            results.append(
                EvidenceResult(
                    source=self.name,
                    title=title,
                    url=f"https://clinicaltrials.gov/study/{nct_id}",
                    identifier=nct_id,
                    snippet=summary[:_MAX_SNIPPET_CHARS] if summary else None,
                    published_date=_parse_study_date(start_date),
                )
            )
        return [r.to_cache_dict() for r in results]
