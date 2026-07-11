"""openFDA label-derived drug-drug interaction fallback (blueprint §9,
ADR-0004) — used only when the DDInter 2.0 pinned snapshot has no record
for a pair. Deliberately a separate client from
app/evidence/connectors/openfda.py's ``OpenFdaConnector`` (Evidence-domain,
searches indications/warnings) — this one searches a label's
``drug_interactions`` section specifically for a mention of the other drug
in the pair.

Not a structured interaction: openFDA has no drug-pair interaction
endpoint, only free-text label sections. This surfaces the FDA's own label
language rather than synthesizing a new claim — an honest "the label
mentions this, a clinician should read it," tagged
``FindingSeverity.UNCLASSIFIED`` (not a DDInter-computed severity tier the
source didn't provide — CLAUDE.md: never state a fact with more confidence
than the source supports)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from app.medication.cache import get_or_fetch
from app.providers.budget import TokenBucket

_MAX_SNIPPET_CHARS = 500
_SNIPPET_CONTEXT_CHARS_BEFORE = 100
_SNIPPET_CONTEXT_CHARS_AFTER = 300


@dataclass(frozen=True, slots=True)
class OpenFdaDdiMatch:
    label_id: str
    url: str
    snippet: str


class OpenFdaDdiClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        redis: Redis,
        cache_ttl_seconds: int,
        max_rpm: float,
        transport: httpx.AsyncBaseTransport | None = None,
        enabled: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._redis = redis
        self._cache_ttl_seconds = cache_ttl_seconds
        self._bucket = TokenBucket(capacity=max_rpm, refill_rate_per_second=max_rpm / 60)
        self._transport = transport
        # ollama_only deployments (ADR-0024) disable this client entirely —
        # check_pair() short-circuits before the cache or the network, using
        # the same "None is a normal, non-error result" contract below.
        self._enabled = enabled

    async def check_pair(self, label_drug: str, mentioned_drug: str) -> OpenFdaDdiMatch | None:
        """Searches ``label_drug``'s own FDA label for a mention of
        ``mentioned_drug`` in its drug-interactions section. Checks one
        direction only — label authors don't cross-reference symmetrically,
        so a caller wanting full pairwise coverage checks both directions
        (app/medication/interactions.py does)."""
        if not self._enabled:
            return None

        async def fetch() -> dict[str, object] | None:
            if not self._bucket.try_consume():
                return None
            return await self._fetch_from_api(label_drug, mentioned_drug)

        cached = await get_or_fetch(
            self._redis,
            source="openfda_ddi",
            query=f"{label_drug}:{mentioned_drug}",
            ttl_seconds=self._cache_ttl_seconds,
            fetch=fetch,
        )
        if cached is None:
            return None
        return OpenFdaDdiMatch(
            label_id=str(cached["label_id"]),
            url=str(cached["url"]),
            snippet=str(cached["snippet"]),
        )

    async def _fetch_from_api(
        self, label_drug: str, mentioned_drug: str
    ) -> dict[str, object] | None:
        escaped = label_drug.replace('"', '\\"')
        params: dict[str, str | int] = {
            "search": f'openfda.generic_name:"{escaped}"',
            "limit": 1,
        }
        if self._api_key:
            params["api_key"] = self._api_key

        async with httpx.AsyncClient(timeout=10.0, transport=self._transport) as client:
            response = await client.get(f"{self._base_url}/drug/label.json", params=params)
        if response.status_code >= 400:
            # openFDA returns 404 for a zero-result search, not an error
            # payload — the same as "nothing found," never a real failure.
            return None

        data = response.json()
        results = data.get("results") or []
        if not results:
            return None
        record = results[0]
        label_id = record.get("id")
        if not label_id:
            return None

        interaction_sections = record.get("drug_interactions") or []
        text = " ".join(interaction_sections)
        lowered = text.lower()
        needle = mentioned_drug.lower()
        position = lowered.find(needle)
        if position == -1:
            return None

        start = max(0, position - _SNIPPET_CONTEXT_CHARS_BEFORE)
        end = position + len(needle) + _SNIPPET_CONTEXT_CHARS_AFTER
        snippet = text[start:end][:_MAX_SNIPPET_CHARS]

        return {
            "label_id": label_id,
            "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={label_id}",
            "snippet": snippet,
        }
