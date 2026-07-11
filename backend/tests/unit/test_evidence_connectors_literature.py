"""Unit tests for the PubMed and ClinicalTrials.gov literature/trial
connectors, against httpx.MockTransport plus the real Redis client from the
``app`` fixture."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from app.data.models.evidence import EvidenceSourceName
from app.evidence.connectors.clinicaltrials import ClinicalTrialsConnector
from app.evidence.connectors.pubmed import PubMedConnector

pytestmark = pytest.mark.unit


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


# ── PubMed ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pubmed_search_retries_after_a_transient_server_error(app) -> None:  # type: ignore[no-untyped-def]
    """Regression: a 5xx from e-utilities used to be cached as an empty
    result for the full TTL — a transient outage silently became "no
    evidence" for 24 hours."""
    query = f"metformin transient-{uuid.uuid4()}"
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(500)
        if request.url.path.endswith("/esearch.fcgi"):
            return httpx.Response(
                200, content=json.dumps({"esearchresult": {"idlist": ["12345678"]}})
            )
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "result": {
                        "uids": ["12345678"],
                        "12345678": {
                            "title": "Metformin in type 2 diabetes: a review",
                            "pubdate": "2023 Jun 15",
                            "source": "Diabetes Care",
                        },
                    }
                }
            ),
        )

    connector = PubMedConnector(
        base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        api_key=None,
        email="test@example.com",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=10,
        transport=_transport(handler),
    )
    assert await connector.search(query) == []
    results = await connector.search(query)
    assert len(results) == 1
    assert results[0].identifier == "12345678"


@pytest.mark.asyncio
async def test_pubmed_search_returns_citations_via_esearch_then_esummary(app) -> None:  # type: ignore[no-untyped-def]
    query = f"metformin diabetes-{uuid.uuid4()}"
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/esearch.fcgi"):
            return httpx.Response(
                200, content=json.dumps({"esearchresult": {"idlist": ["12345678"]}})
            )
        assert request.url.path.endswith("/esummary.fcgi")
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "result": {
                        "uids": ["12345678"],
                        "12345678": {
                            "title": "Metformin in type 2 diabetes: a review",
                            "pubdate": "2023 Jun 15",
                            "source": "Diabetes Care",
                        },
                    }
                }
            ),
        )

    connector = PubMedConnector(
        base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        api_key=None,
        email="test@example.com",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=10,
        transport=_transport(handler),
    )
    results = await connector.search(query)

    assert calls == ["/entrez/eutils/esearch.fcgi", "/entrez/eutils/esummary.fcgi"]
    assert len(results) == 1
    result = results[0]
    assert result.source == EvidenceSourceName.PUBMED
    assert result.title == "Metformin in type 2 diabetes: a review"
    assert result.identifier == "12345678"
    assert result.url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert result.published_date is not None
    assert result.published_date.isoformat() == "2023-06-15"


@pytest.mark.asyncio
async def test_pubmed_search_returns_empty_when_esearch_finds_nothing(app) -> None:  # type: ignore[no-untyped-def]
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/esearch.fcgi")
        return httpx.Response(200, content=json.dumps({"esearchresult": {"idlist": []}}))

    connector = PubMedConnector(
        base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        api_key=None,
        email="test@example.com",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=10,
        transport=_transport(handler),
    )
    results = await connector.search(f"nonexistent-{uuid.uuid4()}")
    assert results == []


@pytest.mark.asyncio
async def test_pubmed_search_returns_empty_when_rate_limited_without_calling_api(app) -> None:  # type: ignore[no-untyped-def]
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=json.dumps({"esearchresult": {"idlist": []}}))

    connector = PubMedConnector(
        base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        api_key=None,
        email="test@example.com",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=0,
        transport=_transport(handler),
    )
    results = await connector.search(f"rate-limited-{uuid.uuid4()}")

    assert results == []
    assert called is False


# ── ClinicalTrials.gov ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clinicaltrials_search_returns_study_evidence(app) -> None:  # type: ignore[no-untyped-def]
    query = f"type 2 diabetes-{uuid.uuid4()}"
    body = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT01234567",
                        "briefTitle": "A Study of Metformin in Type 2 Diabetes",
                    },
                    "descriptionModule": {"briefSummary": "This study evaluates metformin..."},
                    "statusModule": {"startDateStruct": {"date": "2020-03"}},
                }
            }
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/studies")
        return httpx.Response(200, content=json.dumps(body))

    connector = ClinicalTrialsConnector(
        base_url="https://clinicaltrials.gov/api/v2",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=5,
        transport=_transport(handler),
    )
    results = await connector.search(query)

    assert len(results) == 1
    result = results[0]
    assert result.source == EvidenceSourceName.CLINICALTRIALS
    assert result.title == "A Study of Metformin in Type 2 Diabetes"
    assert result.identifier == "NCT01234567"
    assert result.url == "https://clinicaltrials.gov/study/NCT01234567"
    assert result.published_date is not None
    assert result.published_date.isoformat() == "2020-03-01"


@pytest.mark.asyncio
async def test_clinicaltrials_search_returns_empty_on_http_error(app) -> None:  # type: ignore[no-untyped-def]
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"")

    connector = ClinicalTrialsConnector(
        base_url="https://clinicaltrials.gov/api/v2",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=5,
        transport=_transport(handler),
    )
    results = await connector.search(f"unreachable-{uuid.uuid4()}")
    assert results == []
