"""Unit tests for the evidence cache-first fetch helper (ADR-0017) and
EvidenceResult's cache round-trip serialization. Uses the real Redis client
from the ``app`` fixture (same pattern as other cache-adjacent
infrastructure in this codebase — no Redis mock exists here, and this repo
already requires a live Redis for every test run)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from app.data.models.evidence import EvidenceSourceName
from app.evidence.cache import get_or_fetch
from app.evidence.connectors.base import EvidenceResult

pytestmark = pytest.mark.unit


def test_evidence_result_cache_round_trip_preserves_every_field() -> None:
    result = EvidenceResult(
        source=EvidenceSourceName.PUBMED,
        title="Metformin in type 2 diabetes",
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        identifier="12345678",
        snippet="Metformin remains first-line therapy...",
        published_date=date(2023, 6, 1),
    )
    restored = EvidenceResult.from_cache_dict(result.to_cache_dict())
    assert restored == result


def test_evidence_result_cache_round_trip_handles_missing_optional_fields() -> None:
    result = EvidenceResult(
        source=EvidenceSourceName.MESH,
        title="Diabetes Mellitus, Type 2",
        url=None,
        identifier=None,
        snippet=None,
        published_date=None,
    )
    restored = EvidenceResult.from_cache_dict(result.to_cache_dict())
    assert restored == result


@pytest.mark.asyncio
async def test_get_or_fetch_calls_fetch_on_first_call_only(app) -> None:  # type: ignore[no-untyped-def]
    # A fresh, unique query per test run — this repo's tests share a real,
    # persistent local Redis (no per-test flush, unlike the Postgres
    # `_clean_tables` fixture), so a fixed literal query would silently hit
    # a stale entry from a previous local run instead of exercising a real
    # first-call miss.
    query = f"unique query {uuid.uuid4()}"
    call_count = 0

    async def fetch() -> list[dict[str, object]]:
        nonlocal call_count
        call_count += 1
        return [{"title": "Result A"}]

    redis = app.state.redis
    first = await get_or_fetch(
        redis, source="test-source", query=query, ttl_seconds=60, fetch=fetch
    )
    second = await get_or_fetch(
        redis, source="test-source", query=query, ttl_seconds=60, fetch=fetch
    )

    assert first == [{"title": "Result A"}]
    assert second == [{"title": "Result A"}]
    assert call_count == 1, "fetch should only run once — the second call must hit the cache"


@pytest.mark.asyncio
async def test_get_or_fetch_uses_separate_cache_entries_per_query(app) -> None:  # type: ignore[no-untyped-def]
    query_a = f"query A {uuid.uuid4()}"
    query_b = f"query B {uuid.uuid4()}"

    async def fetch_a() -> list[dict[str, object]]:
        return [{"title": "A"}]

    async def fetch_b() -> list[dict[str, object]]:
        return [{"title": "B"}]

    redis = app.state.redis
    result_a = await get_or_fetch(
        redis, source="test-source", query=query_a, ttl_seconds=60, fetch=fetch_a
    )
    result_b = await get_or_fetch(
        redis, source="test-source", query=query_b, ttl_seconds=60, fetch=fetch_b
    )

    assert result_a == [{"title": "A"}]
    assert result_b == [{"title": "B"}]
