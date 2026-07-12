"""Local embedding model (docs/ENVIRONMENT.md EMBEDDING_MODEL_ID/DEVICE).
BGE models want a query-side instruction prefix for asymmetric retrieval
quality; passage embeddings use the raw text. Vectors are L2-normalized so
cosine distance (the HNSW index's metric, ADR-0015) is well-defined."""

from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.logging import get_logger

logger = get_logger(__name__)

_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingModel:
    def __init__(self, model_id: str, device: str, *, offline_only: bool = False) -> None:
        self._model_id = model_id
        # Local HF cache first: a cached model must never trigger outbound
        # huggingface.co requests — they add ~20s of HEAD-call latency to
        # every cold start, and in ollama_only mode (ADR-0024) any outbound
        # call violates the deployment's air-gap/data-residency guarantee.
        try:
            self._model = SentenceTransformer(model_id, device=device, local_files_only=True)
        except Exception as exc:
            if offline_only:
                raise RuntimeError(
                    f"Embedding model {model_id!r} is not in the local HuggingFace cache and "
                    "DEPLOYMENT_MODE=ollama_only forbids downloading it — pre-populate the "
                    "cache (e.g. bake the model into the image) before starting."
                ) from exc
            # First run on a standard deployment: download once, cached for
            # every subsequent (offline-capable) load.
            logger.info("embedding_model_not_cached_downloading", model_id=model_id)
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


def get_embedding_model(
    model_id: str, device: str, *, offline_only: bool = False
) -> EmbeddingModel:
    """Process-wide singleton, keyed on (model_id, device, offline_only) —
    loading SentenceTransformer is expensive (model weights from disk/HF
    cache); never reload per-request. Keyed on primitives, not the Settings
    object, since Pydantic models are not hashable by default. The cached
    inner function takes ``offline_only`` positionally so keyword and
    positional call styles share one cache entry (lru_cache keys them
    differently, which would thrash a maxsize=1 cache)."""
    return _get_embedding_model_cached(model_id, device, offline_only)


@lru_cache(maxsize=1)
def _get_embedding_model_cached(model_id: str, device: str, offline_only: bool) -> EmbeddingModel:
    return EmbeddingModel(model_id, device, offline_only=offline_only)
