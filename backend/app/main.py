"""FastAPI application factory (docs/ARCHITECTURE.md §3.2, §9)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth as auth_router
from app.api.routers import chats as chats_router
from app.api.routers import health as health_router
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
from app.core.tracing import configure_tracing, instrument_app
from app.data.base import Database

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    configure_tracing(settings)

    app.state.db = Database(settings)
    app.state.redis = create_redis_client(settings)

    logger.info("startup_complete", env=settings.CORVEON_ENV)
    yield

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

    if settings.PROMETHEUS_METRICS_ENABLED:
        mount_metrics(app)

    instrument_app(app)
    return app


app = create_app()
