"""Evidence connector registry (blueprint §8) — built once per process
(app.state, mirroring the provider registry, app/providers/registry.py).
Unlike LLM providers, no connector is ever "absent": all six are free
public APIs that work with or without an optional key, so every connector
is always registered; a connector that's temporarily rate-limited or
unreachable returns an empty list for that one search (handled inside each
connector), never raising out of this registry."""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis

from app.core.config import Settings
from app.data.models.evidence import EvidenceSourceName
from app.evidence.connectors.base import EvidenceConnector, EvidenceResult
from app.evidence.connectors.clinicaltrials import ClinicalTrialsConnector
from app.evidence.connectors.dailymed import DailyMedConnector
from app.evidence.connectors.mesh import MeshConnector
from app.evidence.connectors.openfda import OpenFdaConnector
from app.evidence.connectors.pubmed import PubMedConnector
from app.evidence.connectors.rxnorm import RxNormConnector


class EvidenceConnectorRegistry:
    def __init__(self, connectors: dict[EvidenceSourceName, EvidenceConnector]) -> None:
        self._connectors = connectors

    def __getitem__(self, source: EvidenceSourceName) -> EvidenceConnector:
        return self._connectors[source]

    @property
    def sources(self) -> list[EvidenceSourceName]:
        return list(self._connectors)

    async def search_all(
        self, query: str, *, limit_per_source: int = 3
    ) -> dict[EvidenceSourceName, list[EvidenceResult]]:
        """Fans out to every connector concurrently. A connector raising is
        a bug in that connector (every connector's own contract is to
        return ``[]`` rather than raise for a normal not-found/rate-limited
        case, see base.py) — surfaced here rather than swallowed, so a real
        defect is visible instead of silently looking like "no evidence"."""
        names = list(self._connectors)
        results = await asyncio.gather(
            *(self._connectors[name].search(query, limit=limit_per_source) for name in names)
        )
        return dict(zip(names, results, strict=True))


def build_evidence_connector_registry(
    settings: Settings, redis: Redis
) -> EvidenceConnectorRegistry:
    ttl = settings.EVIDENCE_CACHE_TTL_SECONDS
    connectors: dict[EvidenceSourceName, EvidenceConnector] = {
        EvidenceSourceName.PUBMED: PubMedConnector(
            base_url=settings.NCBI_EUTILS_BASE_URL,
            api_key=settings.NCBI_EUTILS_API_KEY,
            email=settings.NCBI_EUTILS_EMAIL,
            redis=redis,
            cache_ttl_seconds=ttl,
            max_rps=settings.NCBI_EUTILS_MAX_RPS,
        ),
        EvidenceSourceName.DAILYMED: DailyMedConnector(
            base_url=settings.DAILYMED_BASE_URL,
            redis=redis,
            cache_ttl_seconds=ttl,
            max_rps=settings.DAILYMED_MAX_RPS,
        ),
        EvidenceSourceName.OPENFDA: OpenFdaConnector(
            base_url=settings.OPENFDA_BASE_URL,
            api_key=settings.OPENFDA_API_KEY,
            redis=redis,
            cache_ttl_seconds=ttl,
            max_rpm=settings.OPENFDA_MAX_RPM,
        ),
        EvidenceSourceName.CLINICALTRIALS: ClinicalTrialsConnector(
            base_url=settings.CLINICALTRIALS_BASE_URL,
            redis=redis,
            cache_ttl_seconds=ttl,
            max_rps=settings.CLINICALTRIALS_MAX_RPS,
        ),
        EvidenceSourceName.MESH: MeshConnector(
            base_url=settings.MESH_BASE_URL,
            redis=redis,
            cache_ttl_seconds=ttl,
            max_rps=settings.MESH_MAX_RPS,
        ),
        EvidenceSourceName.RXNORM: RxNormConnector(
            base_url=settings.RXNAV_BASE_URL,
            redis=redis,
            cache_ttl_seconds=ttl,
            max_rps=settings.RXNAV_MAX_RPS,
        ),
    }
    return EvidenceConnectorRegistry(connectors)
