"""Local embedding model (docs/ENVIRONMENT.md EMBEDDING_MODEL_ID/DEVICE).
BGE models want a query-side instruction prefix for asymmetric retrieval
quality; passage embeddings use the raw text. Vectors are L2-normalized so
cosine distance (the HNSW index's metric, ADR-0015) is well-defined."""

from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingModel:
    def __init__(self, model_id: str, device: str) -> None:
        self._model_id = model_id
        self._model = SentenceTransformer(model_id, device=device)

    @property
    def model_id(self) -> str:
        return self._model_id

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self._model.encode(
            _BGE_QUERY_PREFIX + text, normalize_embeddings=True, convert_to_numpy=True
        )
        return vector.tolist()  # type: ignore[no-any-return]


@lru_cache(maxsize=1)
def get_embedding_model(model_id: str, device: str) -> EmbeddingModel:
    """Process-wide singleton, keyed on (model_id, device) — loading
    SentenceTransformer is expensive (model weights from disk/HF cache);
    never reload per-request. Keyed on primitives, not the Settings object,
    since Pydantic models are not hashable by default."""
    return EmbeddingModel(model_id, device)
