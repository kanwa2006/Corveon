"""PubMed/PMC connector (blueprint §8) — literature evidence via NCBI
E-utilities. A search is two calls (esearch for matching PMIDs, esummary for
their metadata) — E-utilities has no single "search with full metadata"
endpoint, unlike RxNav's ``/drugs.json`` or ClinicalTrials.gov's v2 API."""

from __future__ import annotations

import re
from datetime import date

import httpx
from redis.asyncio import Redis

from app.data.models.evidence import EvidenceSourceName
from app.evidence.cache import UNAVAILABLE, Unavailable, get_or_fetch
from app.evidence.connectors.base import EvidenceResult
from app.providers.budget import TokenBucket

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _parse_pubdate(raw: str | None) -> date | None:
    """PubMed's ``pubdate`` is free text: "2023 Jun 15", "2023 Jun", "2023",
    even "2023 Jun-Jul". Extracts what it can rather than discarding a whole
    citation's date because the day (or month) isn't resolvable — a
    year-only date is still real, useful provenance."""
    if not raw:
        return None
    match = re.match(r"(\d{4})(?:\s+([A-Za-z]{3}))?(?:\s+(\d{1,2}))?", raw.strip())
    if not match:
        return None
    year = int(match.group(1))
    month = _MONTHS.get(match.group(2).lower(), 1) if match.group(2) else 1
    day = int(match.group(3)) if match.group(3) else 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


class PubMedConnector:
    name = EvidenceSourceName.PUBMED

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        email: str | None,
        redis: Redis,
        cache_ttl_seconds: int,
        max_rps: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._email = email
        self._redis = redis
        self._cache_ttl_seconds = cache_ttl_seconds
        self._bucket = TokenBucket(capacity=max_rps, refill_rate_per_second=max_rps)
        self._transport = transport

    def _common_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self._api_key:
            params["api_key"] = self._api_key
        if self._email:
            params["email"] = self._email
        return params

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
            esearch = await client.get(
                f"{self._base_url}/esearch.fcgi",
                params={
                    **self._common_params(),
                    "db": "pubmed",
                    "term": query,
                    "retmax": limit,
                    "retmode": "json",
                },
            )
            if esearch.status_code >= 400:
                return UNAVAILABLE
            pmids: list[str] = esearch.json().get("esearchresult", {}).get("idlist") or []
            if not pmids:
                return []

            esummary = await client.get(
                f"{self._base_url}/esummary.fcgi",
                params={
                    **self._common_params(),
                    "db": "pubmed",
                    "id": ",".join(pmids),
                    "retmode": "json",
                },
            )
            if esummary.status_code >= 400:
                return UNAVAILABLE

        summary_result = esummary.json().get("result", {})
        results: list[EvidenceResult] = []
        for pmid in pmids:
            record = summary_result.get(pmid)
            if not record or not record.get("title"):
                continue
            results.append(
                EvidenceResult(
                    source=self.name,
                    title=record["title"],
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    identifier=pmid,
                    snippet=record.get("source"),
                    published_date=_parse_pubdate(record.get("pubdate")),
                )
            )
        return [r.to_cache_dict() for r in results]
