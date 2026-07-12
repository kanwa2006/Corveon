"""Unit tests for the local embedding model (app/ingestion/embeddings.py).
Uses the real sentence-transformers model (settings default,
BAAI/bge-small-en-v1.5) — the point is to verify the actual integration
(dimension, normalization, query-prefix convention), not a mock of it."""

from __future__ import annotations

import math

import pytest
from app.core.config import get_settings
from app.ingestion.embeddings import get_embedding_model

pytestmark = pytest.mark.unit


def _model():  # type: ignore[no-untyped-def]
    settings = get_settings()
    return get_embedding_model(settings.EMBEDDING_MODEL_ID, settings.EMBEDDING_DEVICE)


def test_embed_passages_returns_384_dim_normalized_vectors() -> None:
    model = _model()
    vectors = model.embed_passages(["Metformin is used to treat type 2 diabetes."])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384
    norm = math.sqrt(sum(x * x for x in vectors[0]))
    assert norm == pytest.approx(1.0, abs=1e-3)


def test_embed_passages_empty_list_returns_empty_list() -> None:
    assert _model().embed_passages([]) == []


def test_embed_query_returns_384_dim_normalized_vector() -> None:
    model = _model()
    vector = model.embed_query("What medication treats diabetes?")
    assert len(vector) == 384
    norm = math.sqrt(sum(x * x for x in vector))
    assert norm == pytest.approx(1.0, abs=1e-3)


def test_semantically_similar_texts_are_closer_than_unrelated_ones() -> None:
    model = _model()
    query = model.embed_query("What medication treats type 2 diabetes?")
    relevant = model.embed_passages(["Metformin is a first-line treatment for type 2 diabetes."])[0]
    unrelated = model.embed_passages(["The Eiffel Tower is located in Paris, France."])[0]

    def cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert cosine(query, relevant) > cosine(query, unrelated)


def test_get_embedding_model_is_a_cached_singleton() -> None:
    settings = get_settings()
    first = get_embedding_model(settings.EMBEDDING_MODEL_ID, settings.EMBEDDING_DEVICE)
    second = get_embedding_model(settings.EMBEDDING_MODEL_ID, settings.EMBEDDING_DEVICE)
    assert first is second


def test_offline_only_raises_instead_of_downloading_an_uncached_model() -> None:
    """Regression (N6, ADR-0024): in ollama_only mode a model missing from
    the local HuggingFace cache must be a hard, explanatory error — never a
    silent outbound download that violates the air-gap guarantee."""
    with pytest.raises(RuntimeError, match="ollama_only"):
        get_embedding_model("corveon-test/definitely-not-a-cached-model", "cpu", offline_only=True)
