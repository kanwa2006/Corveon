"""Unit tests for app/medication/rxnorm_client.py, against
httpx.MockTransport plus the real Redis client from the ``app`` fixture for
the cache-first behavior (same pattern as
test_evidence_connectors_normalization.py)."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from app.medication.rxnorm_client import RxNormClient

pytestmark = pytest.mark.unit


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_normalize_returns_the_first_matching_rxcui(app) -> None:  # type: ignore[no-untyped-def]
    query = f"metformin-{uuid.uuid4()}"
    body = {
        "drugGroup": {
            "conceptGroup": [
                {"tty": "IN", "conceptProperties": [{"rxcui": "6809", "name": "Metformin"}]},
            ],
        }
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/drugs.json")
        return httpx.Response(200, content=json.dumps(body))

    client = RxNormClient(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
    )
    match = await client.normalize(query)

    assert match is not None
    assert match.rxcui == "6809"
    assert match.canonical_name == "Metformin"


@pytest.mark.asyncio
async def test_normalize_returns_none_for_no_match(app) -> None:  # type: ignore[no-untyped-def]
    query = f"not-a-real-drug-{uuid.uuid4()}"
    body = {"drugGroup": {}}

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(body))

    client = RxNormClient(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
    )
    assert await client.normalize(query) is None


@pytest.mark.asyncio
async def test_normalize_falls_back_to_approximate_match_for_misspelled_name(app) -> None:  # type: ignore[no-untyped-def]
    """Blueprint §9 requires typo-tolerant matching via getApproximateMatch:
    a misspelled name that getDrugs can't resolve must still normalize, or
    the drug silently bypasses every downstream safety check."""
    query = f"metformn-{uuid.uuid4()}"
    approximate_body = {
        "approximateGroup": {
            "candidate": [
                {"rxcui": "6809", "score": "8.18", "rank": "1", "name": "metformin"},
            ],
        }
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/drugs.json"):
            return httpx.Response(200, content=json.dumps({"drugGroup": {}}))
        assert request.url.path.endswith("/approximateTerm.json")
        return httpx.Response(200, content=json.dumps(approximate_body))

    client = RxNormClient(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
    )
    match = await client.normalize(query)

    assert match is not None
    assert match.rxcui == "6809"
    assert match.canonical_name == "metformin"


@pytest.mark.asyncio
async def test_approximate_match_resolves_canonical_name_when_candidate_lacks_one(app) -> None:  # type: ignore[no-untyped-def]
    query = f"metformn-nameless-{uuid.uuid4()}"
    approximate_body = {
        "approximateGroup": {
            "candidate": [{"rxcui": "6809", "score": "8.18", "rank": "1"}],
        }
    }
    property_body = {
        "propConceptGroup": {
            "propConcept": [
                {"propCategory": "NAMES", "propName": "RxNorm Name", "propValue": "metformin"},
            ],
        }
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/drugs.json"):
            return httpx.Response(200, content=json.dumps({"drugGroup": {}}))
        if request.url.path.endswith("/approximateTerm.json"):
            return httpx.Response(200, content=json.dumps(approximate_body))
        assert request.url.path.endswith("/rxcui/6809/property.json")
        return httpx.Response(200, content=json.dumps(property_body))

    client = RxNormClient(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
    )
    match = await client.normalize(query)

    assert match is not None
    assert match.rxcui == "6809"
    assert match.canonical_name == "metformin"


@pytest.mark.asyncio
async def test_normalize_returns_none_when_approximate_match_has_no_candidates(app) -> None:  # type: ignore[no-untyped-def]
    query = f"gibberish-{uuid.uuid4()}"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/drugs.json"):
            return httpx.Response(200, content=json.dumps({"drugGroup": {}}))
        assert request.url.path.endswith("/approximateTerm.json")
        return httpx.Response(200, content=json.dumps({"approximateGroup": {}}))

    client = RxNormClient(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
    )
    assert await client.normalize(query) is None


@pytest.mark.asyncio
async def test_normalize_returns_none_on_http_error_without_raising(app) -> None:  # type: ignore[no-untyped-def]
    query = f"error-drug-{uuid.uuid4()}"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = RxNormClient(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
    )
    assert await client.normalize(query) is None


@pytest.mark.asyncio
async def test_normalize_caches_the_result_and_does_not_refetch(app) -> None:  # type: ignore[no-untyped-def]
    query = f"cached-drug-{uuid.uuid4()}"
    body = {
        "drugGroup": {
            "conceptGroup": [
                {"tty": "IN", "conceptProperties": [{"rxcui": "1191", "name": "Aspirin"}]},
            ],
        }
    }
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, content=json.dumps(body))

    client = RxNormClient(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
    )
    first = await client.normalize(query)
    second = await client.normalize(query)

    assert first == second
    assert call_count == 1


@pytest.mark.asyncio
async def test_normalize_returns_none_when_rate_limit_bucket_is_exhausted(app) -> None:  # type: ignore[no-untyped-def]
    query = f"rate-limited-drug-{uuid.uuid4()}"

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not be called when the bucket is exhausted")

    client = RxNormClient(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=0,
        transport=_transport(handler),
    )
    assert await client.normalize(query) is None


@pytest.mark.asyncio
async def test_normalize_returns_none_without_any_network_call_when_disabled(app) -> None:  # type: ignore[no-untyped-def]
    """ollama_only deployments (ADR-0024) construct this client with
    enabled=False — normalize() must never reach the network, cache, or
    rate limiter, not even to check the cache first."""
    query = f"disabled-client-drug-{uuid.uuid4()}"

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not be called when the client is disabled")

    client = RxNormClient(
        base_url="https://rxnav.nlm.nih.gov/REST",
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rps=20,
        transport=_transport(handler),
        enabled=False,
    )
    assert await client.normalize(query) is None
