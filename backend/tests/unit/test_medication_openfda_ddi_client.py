"""Unit tests for app/medication/openfda_ddi_client.py, against
httpx.MockTransport plus the real Redis client from the ``app`` fixture."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from app.medication.openfda_ddi_client import OpenFdaDdiClient

pytestmark = pytest.mark.unit


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_check_pair_finds_a_mention_in_the_interactions_section(app) -> None:  # type: ignore[no-untyped-def]
    label_drug = f"warfarin-{uuid.uuid4()}"
    mentioned_drug = "aspirin"
    body = {
        "results": [
            {
                "id": "label-123",
                "drug_interactions": [
                    "Concomitant use with aspirin increases the risk of bleeding."
                ],
            }
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/drug/label.json")
        return httpx.Response(200, content=json.dumps(body))

    client = OpenFdaDdiClient(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=240,
        transport=_transport(handler),
    )
    match = await client.check_pair(label_drug, mentioned_drug)

    assert match is not None
    assert match.label_id == "label-123"
    assert "aspirin" in match.snippet.lower()
    assert match.url == "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=label-123"


@pytest.mark.asyncio
async def test_check_pair_returns_none_when_mentioned_drug_is_absent(app) -> None:  # type: ignore[no-untyped-def]
    label_drug = f"metformin-{uuid.uuid4()}"
    body = {
        "results": [
            {"id": "label-456", "drug_interactions": ["No significant interactions known."]}
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(body))

    client = OpenFdaDdiClient(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=240,
        transport=_transport(handler),
    )
    assert await client.check_pair(label_drug, "some-other-drug") is None


@pytest.mark.asyncio
async def test_check_pair_returns_none_for_zero_results(app) -> None:  # type: ignore[no-untyped-def]
    label_drug = f"unknown-drug-{uuid.uuid4()}"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = OpenFdaDdiClient(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=240,
        transport=_transport(handler),
    )
    assert await client.check_pair(label_drug, "aspirin") is None


@pytest.mark.asyncio
async def test_check_pair_returns_none_when_rate_limit_bucket_is_exhausted(app) -> None:  # type: ignore[no-untyped-def]
    label_drug = f"rate-limited-{uuid.uuid4()}"

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not be called when the bucket is exhausted")

    client = OpenFdaDdiClient(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=0,
        transport=_transport(handler),
    )
    assert await client.check_pair(label_drug, "aspirin") is None


@pytest.mark.asyncio
async def test_a_zero_result_404_is_cached_as_a_no_match(app) -> None:  # type: ignore[no-untyped-def]
    """openFDA's 404 means "nothing found" (a real answer, cached) — unlike
    a 5xx, which is the source being unreachable (never cached)."""
    label_drug = f"unknown-drug-{uuid.uuid4()}"
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(404)

    client = OpenFdaDdiClient(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=240,
        transport=_transport(handler),
    )
    assert await client.check_pair(label_drug, "aspirin") is None
    assert await client.check_pair(label_drug, "aspirin") is None
    assert call_count == 1


@pytest.mark.asyncio
async def test_a_server_error_is_not_cached_as_a_no_match(app) -> None:  # type: ignore[no-untyped-def]
    """Regression: a 5xx/429 used to be cached as a no-match for the full
    TTL, silently hiding a label-mentioned interaction until expiry."""
    label_drug = f"warfarin-{uuid.uuid4()}"
    body = {
        "results": [
            {
                "id": "label-123",
                "drug_interactions": [
                    "Concomitant use with aspirin increases the risk of bleeding."
                ],
            }
        ]
    }
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(500)
        return httpx.Response(200, content=json.dumps(body))

    client = OpenFdaDdiClient(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=240,
        transport=_transport(handler),
    )
    assert await client.check_pair(label_drug, "aspirin") is None
    match = await client.check_pair(label_drug, "aspirin")
    assert match is not None
    assert match.label_id == "label-123"


@pytest.mark.asyncio
async def test_a_rate_limited_check_is_not_cached_as_a_no_match(app) -> None:  # type: ignore[no-untyped-def]
    label_drug = f"warfarin-{uuid.uuid4()}"
    body = {
        "results": [
            {
                "id": "label-456",
                "drug_interactions": [
                    "Concomitant use with aspirin increases the risk of bleeding."
                ],
            }
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(body))

    exhausted = OpenFdaDdiClient(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=0,
        transport=_transport(handler),
    )
    assert await exhausted.check_pair(label_drug, "aspirin") is None

    refilled = OpenFdaDdiClient(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=240,
        transport=_transport(handler),
    )
    match = await refilled.check_pair(label_drug, "aspirin")
    assert match is not None
    assert match.label_id == "label-456"


@pytest.mark.asyncio
async def test_check_pair_returns_none_without_any_network_call_when_disabled(app) -> None:  # type: ignore[no-untyped-def]
    """ollama_only deployments (ADR-0024) construct this client with
    enabled=False — check_pair() must never reach the network, cache, or
    rate limiter, not even to check the cache first."""
    label_drug = f"disabled-client-{uuid.uuid4()}"

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not be called when the client is disabled")

    client = OpenFdaDdiClient(
        base_url="https://api.fda.gov",
        api_key=None,
        redis=app.state.redis,
        cache_ttl_seconds=60,
        max_rpm=240,
        transport=_transport(handler),
        enabled=False,
    )
    assert await client.check_pair(label_drug, "aspirin") is None
