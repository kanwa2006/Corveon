"""Unit tests for the connector registry's fan-out (app/evidence/registry.py)
and the retrieval layer's merge (app/evidence/retrieval.py), against fake
connectors — no real HTTP/Redis needed to test fan-out/merge logic itself
(each real connector's own behavior is already covered by its own test
file)."""

from __future__ import annotations

from datetime import date

import pytest
from app.data.models.evidence import EvidenceSourceName
from app.evidence.connectors.base import EvidenceResult
from app.evidence.registry import EvidenceConnectorRegistry
from app.evidence.retrieval import retrieve_evidence_for_claim

pytestmark = pytest.mark.unit


class _FakeConnector:
    def __init__(self, name: EvidenceSourceName, results: list[EvidenceResult]) -> None:
        self.name = name
        self._results = results
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, *, limit: int = 5) -> list[EvidenceResult]:
        self.calls.append((query, limit))
        return self._results[:limit]


def _result(source: EvidenceSourceName, title: str) -> EvidenceResult:
    return EvidenceResult(
        source=source,
        title=title,
        url=None,
        identifier=None,
        snippet=None,
        published_date=date(2024, 1, 1),
    )


@pytest.mark.asyncio
async def test_search_all_queries_every_connector_and_keys_results_by_source() -> None:
    pubmed = _FakeConnector(EvidenceSourceName.PUBMED, [_result(EvidenceSourceName.PUBMED, "P1")])
    mesh = _FakeConnector(EvidenceSourceName.MESH, [_result(EvidenceSourceName.MESH, "M1")])
    registry = EvidenceConnectorRegistry(
        {EvidenceSourceName.PUBMED: pubmed, EvidenceSourceName.MESH: mesh}
    )

    results = await registry.search_all("metformin", limit_per_source=3)

    assert results[EvidenceSourceName.PUBMED][0].title == "P1"
    assert results[EvidenceSourceName.MESH][0].title == "M1"
    assert pubmed.calls == [("metformin", 3)]
    assert mesh.calls == [("metformin", 3)]


@pytest.mark.asyncio
async def test_search_all_a_connector_returning_nothing_does_not_affect_others() -> None:
    empty = _FakeConnector(EvidenceSourceName.RXNORM, [])
    populated = _FakeConnector(
        EvidenceSourceName.OPENFDA, [_result(EvidenceSourceName.OPENFDA, "O1")]
    )
    registry = EvidenceConnectorRegistry(
        {EvidenceSourceName.RXNORM: empty, EvidenceSourceName.OPENFDA: populated}
    )

    results = await registry.search_all("query")

    assert results[EvidenceSourceName.RXNORM] == []
    assert len(results[EvidenceSourceName.OPENFDA]) == 1


@pytest.mark.asyncio
async def test_retrieve_evidence_for_claim_merges_results_across_sources() -> None:
    pubmed = _FakeConnector(EvidenceSourceName.PUBMED, [_result(EvidenceSourceName.PUBMED, "P1")])
    dailymed = _FakeConnector(
        EvidenceSourceName.DAILYMED, [_result(EvidenceSourceName.DAILYMED, "D1")]
    )
    registry = EvidenceConnectorRegistry(
        {EvidenceSourceName.PUBMED: pubmed, EvidenceSourceName.DAILYMED: dailymed}
    )

    merged = await retrieve_evidence_for_claim(
        registry=registry, claim_text="metformin lowers blood glucose"
    )

    titles = {result.title for result in merged}
    assert titles == {"P1", "D1"}


@pytest.mark.asyncio
async def test_retrieve_evidence_for_claim_returns_empty_for_blank_claim_without_querying() -> None:
    connector = _FakeConnector(
        EvidenceSourceName.PUBMED, [_result(EvidenceSourceName.PUBMED, "P1")]
    )
    registry = EvidenceConnectorRegistry({EvidenceSourceName.PUBMED: connector})

    merged = await retrieve_evidence_for_claim(registry=registry, claim_text="   ")

    assert merged == []
    assert connector.calls == []
