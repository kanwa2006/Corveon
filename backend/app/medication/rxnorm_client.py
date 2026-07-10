"""RxNorm/RxNav normalization client for the Medication-Safety Engine
(blueprint §9: "a normalizer maps every drug to RxCUI via RxNorm/RxNav").

Deliberately a separate, minimal client from
app/evidence/connectors/rxnorm.py's ``RxNormConnector`` rather than reused
directly: that connector returns ``EvidenceResult`` objects shaped for the
Evidence Verification Engine's citation model, which this domain has no use
for and shouldn't couple to — medication normalization only ever needs an
RxCUI and a canonical name. Same httpx/Redis-cache/TokenBucket conventions
as every other external client in this codebase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
from redis.asyncio import Redis

from app.medication.cache import get_or_fetch
from app.providers.budget import TokenBucket


@dataclass(frozen=True, slots=True)
class RxNormMatch:
    rxcui: str
    canonical_name: str


class SupportsNormalize(Protocol):
    """Structural seam so callers (normalize_entry) and tests can supply
    any object with this shape — not just a real RxNormClient — matching
    app/evidence/connectors/base.py's EvidenceConnector protocol pattern."""

    async def normalize(self, name: str) -> RxNormMatch | None: ...


class RxNormClient:
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
        # matching every other external client in this codebase.
        self._transport = transport

    async def normalize(self, name: str) -> RxNormMatch | None:
        """Returns the best RxCUI match for ``name``, or ``None`` if RxNav
        has no match — never raises for a normal not-found/rate-limited
        case (matches every evidence connector's own contract), since an
        unmatched drug name is still a usable, honestly-flagged medication
        entry, not a request failure."""

        async def fetch() -> dict[str, object] | None:
            if not self._bucket.try_consume():
                return None
            return await self._fetch_from_api(name)

        cached = await get_or_fetch(
            self._redis,
            source="rxnorm",
            query=name,
            ttl_seconds=self._cache_ttl_seconds,
            fetch=fetch,
        )
        if cached is None:
            return None
        return RxNormMatch(rxcui=str(cached["rxcui"]), canonical_name=str(cached["canonical_name"]))

    async def _fetch_from_api(self, name: str) -> dict[str, object] | None:
        async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
            response = await client.get(f"{self._base_url}/drugs.json", params={"name": name})
        if response.status_code >= 400:
            return None

        data = response.json()
        concept_groups = data.get("drugGroup", {}).get("conceptGroup") or []
        for group in concept_groups:
            for prop in group.get("conceptProperties") or []:
                rxcui = prop.get("rxcui")
                concept_name = prop.get("name")
                if rxcui and concept_name:
                    return {"rxcui": rxcui, "canonical_name": concept_name}
        return None
