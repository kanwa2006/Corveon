"""FastAPI application factory (docs/ARCHITECTURE.md §3.2, §9)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth as auth_router
from app.api.routers import chats as chats_router
from app.api.routers import documents as documents_router
from app.api.routers import evidence as evidence_router
from app.api.routers import health as health_router
from app.api.routers import jobs as jobs_router
from app.api.routers import medication as medication_router
from app.api.routers import messages as messages_router
from app.api.routers import search as search_router
from app.core.arq import create_arq_pool
from app.core.config import get_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging, get_logger
from app.core.metrics import PrometheusMiddleware, mount_metrics
from app.core.middleware import TraceIdMiddleware
from app.core.redis import create_redis_client
from app.core.storage import create_object_storage
from app.core.tracing import configure_tracing, instrument_app
from app.data.base import Database
from app.evidence.registry import EvidenceConnectorRegistry, build_evidence_connector_registry
from app.medication.openfda_ddi_client import OpenFdaDdiClient
from app.medication.rxnorm_client import RxNormClient
from app.providers.registry import build_provider_registry

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    configure_tracing(settings)

    app.state.db = Database(settings)
    app.state.redis = create_redis_client(settings)
    app.state.arq = await create_arq_pool(settings)
    app.state.storage = create_object_storage(settings)
    # Built once per process, not per-request: a fresh registry per request
    # would reset each provider's key-pool round-robin state (itertools.cycle)
    # every time, defeating the point of rotating across a free-tier key pool.
    app.state.provider_registry = build_provider_registry(settings)
    # Every evidence connector is always registered (unlike LLM providers,
    # none of the six public sources has an "absence" state — see
    # app/evidence/registry.py); built once per process for the same reason
    # the provider registry is. Except in ollama_only mode (ADR-0024): an
    # empty registry disables both the Evidence Verification endpoint and
    # the chat orchestrator's public-evidence routing branch at this single
    # choke point — neither consumer needs to know deployment mode exists.
    app.state.evidence_connectors = (
        EvidenceConnectorRegistry({})
        if settings.is_ollama_only
        else build_evidence_connector_registry(settings, app.state.redis)
    )
    # Medication-Safety Engine Phase 1 live lookups — same RxNav/openFDA
    # settings the Evidence connectors use (same public APIs, different
    # domain-scoped clients, see app/medication/rxnorm_client.py's own
    # docstring for why they aren't the same classes). Always registered,
    # like the evidence connectors: neither RxNav nor openFDA has an
    # "absence" state — except in ollama_only mode, where both clients are
    # still constructed but disabled (ADR-0024), never touching the network.
    app.state.rxnorm_client = RxNormClient(
        base_url=settings.RXNAV_BASE_URL,
        redis=app.state.redis,
        cache_ttl_seconds=settings.EVIDENCE_CACHE_TTL_SECONDS,
        max_rps=settings.RXNAV_MAX_RPS,
        enabled=not settings.is_ollama_only,
    )
    app.state.openfda_ddi_client = OpenFdaDdiClient(
        base_url=settings.OPENFDA_BASE_URL,
        api_key=settings.OPENFDA_API_KEY,
        redis=app.state.redis,
        cache_ttl_seconds=settings.EVIDENCE_CACHE_TTL_SECONDS,
        max_rpm=settings.OPENFDA_MAX_RPM,
        enabled=not settings.is_ollama_only,
    )
    # The embedding model is NOT loaded here — it's a lazy, lru_cache'd
    # singleton (app/ingestion/embeddings.py) resolved on first use via
    # EmbeddingModelDep, so endpoints/tests that never touch search or
    # documents never pay the model-load cost.

    logger.info(
        "startup_complete", env=settings.CORVEON_ENV, deployment_mode=settings.DEPLOYMENT_MODE
    )
    yield

    await app.state.arq.aclose()
    await app.state.redis.aclose()
    await app.state.db.dispose()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="Corveon API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(TraceIdMiddleware)

    # FastAPI's add_exception_handler is typed against the base Exception signature;
    # registering narrower handler types is the documented, runtime-correct pattern.
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(health_router.router)
    app.include_router(auth_router.router, prefix="/api/v1")
    app.include_router(chats_router.router, prefix="/api/v1")
    app.include_router(messages_router.router, prefix="/api/v1")
    app.include_router(documents_router.router, prefix="/api/v1")
    app.include_router(jobs_router.router, prefix="/api/v1")
    app.include_router(search_router.router, prefix="/api/v1")
    app.include_router(evidence_router.router, prefix="/api/v1")
    app.include_router(medication_router.router, prefix="/api/v1")

    if settings.PROMETHEUS_METRICS_ENABLED:
        mount_metrics(app)

    instrument_app(app)
    return app


app = create_app()
