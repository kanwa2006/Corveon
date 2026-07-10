"""Common connector protocol (blueprint §8: six public sources, one
interface). New connectors — including an org-trusted-source adapter, once
that subsystem exists — implement this same shape; the retrieval layer
(app/evidence/retrieval.py) fans out to whichever connectors are relevant to
a claim without knowing which concrete source it's talking to."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.data.models.evidence import EvidenceSourceName


@dataclass(frozen=True, slots=True)
class EvidenceResult:
    source: EvidenceSourceName
    title: str
    url: str | None
    identifier: str | None
    snippet: str | None
    published_date: date | None

    def to_cache_dict(self) -> dict[str, object]:
        return {
            "source": self.source.value,
            "title": self.title,
            "url": self.url,
            "identifier": self.identifier,
            "snippet": self.snippet,
            "published_date": self.published_date.isoformat() if self.published_date else None,
        }

    @classmethod
    def from_cache_dict(cls, data: dict[str, object]) -> EvidenceResult:
        # Required fields use `str(...)`/`EvidenceSourceName(...)` directly —
        # a missing or malformed value here means the cache entry is
        # corrupted (this module is the only writer, via to_cache_dict), not
        # a normal case to silently paper over with a guessed default.
        url = data.get("url")
        identifier = data.get("identifier")
        snippet = data.get("snippet")
        published_raw = data.get("published_date")
        return cls(
            source=EvidenceSourceName(str(data["source"])),
            title=str(data["title"]),
            url=url if isinstance(url, str) else None,
            identifier=identifier if isinstance(identifier, str) else None,
            snippet=snippet if isinstance(snippet, str) else None,
            published_date=date.fromisoformat(published_raw)
            if isinstance(published_raw, str)
            else None,
        )


class EvidenceConnector(Protocol):
    name: EvidenceSourceName

    async def search(self, query: str, *, limit: int = 5) -> list[EvidenceResult]:
        """Returns matching evidence records for ``query``, most relevant
        first. An empty list means "nothing found or this source wasn't
        reachable right now" — never raises for a normal not-found or
        rate-limited case; the caller (retrieval layer) treats missing
        coverage from one source as reduced confidence, not a hard error
        (blueprint §8: conflicting/insufficient evidence is itself a
        provenance class, not a failure mode)."""
        ...
