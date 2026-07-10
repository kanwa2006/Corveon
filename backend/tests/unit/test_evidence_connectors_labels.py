"""Unit tests for the openFDA and DailyMed label connectors, against
httpx.MockTransport plus the real Redis client from the ``app`` fixture."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from app.data.models.evidence import EvidenceSourceName
from app.evidence.connectors.dailymed import DailyMedConnector
from app.evidence.connectors.openfda import OpenFdaConnector

pytestmark = pytest.mark.unit


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


# ── openFDA ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_openfda_search_returns_label_evidence(app) -> None:  # type: ignore[no-untyped-def]
    query = f"metformin-{uuid.uuid4()}"
    body = {
        "results": [
            {
                "id": "abc123-setid",
                "effective_time": "20230615",
                "openfda": {"brand_name": ["Glucophage"], "generic_name": ["metformin"]},
                "indications_and_usage": ["Indicated for type 2 diabetes mellitus."],
            }
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/drug/label.json")
        return httpx.Response(200, content=json.dumps(body))

    connector = OpenFdaConnector(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=240,
        transport=_transport(handler),
    )
    results = await connector.search(query)

    assert len(results) == 1
    result = results[0]
    assert result.source == EvidenceSourceName.OPENFDA
    assert result.title == "Glucophage"
    assert result.identifier == "abc123-setid"
    assert result.url == "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=abc123-setid"
    assert result.snippet == "Indicated for type 2 diabetes mellitus."
    assert result.published_date is not None
    assert result.published_date.isoformat() == "2023-06-15"


@pytest.mark.asyncio
async def test_openfda_search_returns_empty_on_404_zero_results(app) -> None:  # type: ignore[no-untyped-def]
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b'{"error": {"code": "NOT_FOUND"}}')

    connector = OpenFdaConnector(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=240,
        transport=_transport(handler),
    )
    results = await connector.search(f"nonexistent-{uuid.uuid4()}")
    assert results == []


@pytest.mark.asyncio
async def test_openfda_search_returns_empty_when_rate_limited_without_calling_api(app) -> None:  # type: ignore[no-untyped-def]
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=json.dumps({"results": []}))

    connector = OpenFdaConnector(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=0,
        transport=_transport(handler),
    )
    results = await connector.search(f"rate-limited-{uuid.uuid4()}")

    assert results == []
    assert called is False


# ── DailyMed ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dailymed_search_returns_spl_evidence(app) -> None:  # type: ignore[no-untyped-def]
    query = f"lisinopril-{uuid.uuid4()}"
    body = {
        "data": [
            {
                "setid": "def456-setid",
                "title": "LISINOPRIL tablet",
                "published_date": "2022-01-10",
            }
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/spls.json")
        return httpx.Response(200, content=json.dumps(body))

    connector = DailyMedConnector(
        base_url="https://dailymed.nlm.nih.gov/dailymed/services/v2",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=5,
        transport=_transport(handler),
    )
    results = await connector.search(query)

    assert len(results) == 1
    result = results[0]
    assert result.source == EvidenceSourceName.DAILYMED
    assert result.title == "LISINOPRIL tablet"
    assert result.identifier == "def456-setid"
    assert result.published_date is not None
    assert result.published_date.isoformat() == "2022-01-10"


@pytest.mark.asyncio
async def test_dailymed_search_returns_empty_on_http_error(app) -> None:  # type: ignore[no-untyped-def]
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"")

    connector = DailyMedConnector(
        base_url="https://dailymed.nlm.nih.gov/dailymed/services/v2",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=5,
        transport=_transport(handler),
    )
    results = await connector.search(f"unreachable-{uuid.uuid4()}")
    assert results == []
