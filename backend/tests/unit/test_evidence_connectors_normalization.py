"""Unit tests for the RxNorm and MeSH normalization connectors, against
httpx.MockTransport (ADR-0006's "testable with fakes" pattern, same as the
LLM provider adapters) plus the real Redis client from the ``app`` fixture
for the cache-first behavior."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from app.data.models.evidence import EvidenceSourceName
from app.evidence.connectors.mesh import MeshConnector
from app.evidence.connectors.rxnorm import RxNormConnector

pytestmark = pytest.mark.unit


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


# ── RxNorm ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rxnorm_search_returns_candidates_from_drugs_endpoint(app) -> None:  # type: ignore[no-untyped-def]
    query = f"metformin-{uuid.uuid4()}"
    body = {
        "drugGroup": {
            "name": query,
            "conceptGroup": [
                {"tty": "IN", "conceptProperties": [{"rxcui": "6809", "name": "Metformin"}]},
                {
                    "tty": "SBD",
                    "conceptProperties": [
                        {
                            "rxcui": "861007",
                            "name": "Metformin hydrochloride 500 MG Oral Tablet",
                        }
                    ],
                },
            ],
        }
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/drugs.json")
        return httpx.Response(200, content=json.dumps(body))

    connector = RxNormConnector(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
    )
    results = await connector.search(query)

    assert len(results) == 2
    assert results[0].source == EvidenceSourceName.RXNORM
    assert results[0].title == "Metformin"
    assert results[0].identifier == "6809"
    assert results[1].identifier == "861007"


@pytest.mark.asyncio
async def test_rxnorm_search_returns_empty_on_http_error(app) -> None:  # type: ignore[no-untyped-def]
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"")

    connector = RxNormConnector(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
    )
    results = await connector.search(f"nonexistent-drug-{uuid.uuid4()}")
    assert results == []


@pytest.mark.asyncio
async def test_rxnorm_search_returns_empty_when_rate_limited_without_calling_api(app) -> None:  # type: ignore[no-untyped-def]
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=json.dumps({"drugGroup": {}}))

    connector = RxNormConnector(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=0,  # bucket always empty
        transport=_transport(handler),
    )
    results = await connector.search(f"rate-limited-{uuid.uuid4()}")

    assert results == []
    assert called is False, "an exhausted rate-limit bucket must never reach the API"


# ── MeSH ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mesh_search_returns_descriptors_from_lookup_endpoint(app) -> None:  # type: ignore[no-untyped-def]
    query = f"diabetes-{uuid.uuid4()}"
    body = [
        {
            "resource": "http://id.nlm.nih.gov/mesh/D003920",
            "label": "Diabetes Mellitus, Type 2",
        }
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/lookup/term")
        return httpx.Response(200, content=json.dumps(body))

    connector = MeshConnector(
        base_url="https://id.nlm.nih.gov/mesh",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=5,
        transport=_transport(handler),
    )
    results = await connector.search(query)

    assert len(results) == 1
    assert results[0].source == EvidenceSourceName.MESH
    assert results[0].title == "Diabetes Mellitus, Type 2"
    assert results[0].identifier == "D003920"
    assert results[0].url == "http://id.nlm.nih.gov/mesh/D003920"


@pytest.mark.asyncio
async def test_mesh_search_returns_empty_on_http_error(app) -> None:  # type: ignore[no-untyped-def]
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"")

    connector = MeshConnector(
        base_url="https://id.nlm.nih.gov/mesh",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=5,
        transport=_transport(handler),
    )
    results = await connector.search(f"unreachable-{uuid.uuid4()}")
    assert results == []
