"""Shared pytest fixtures. Requires a live Postgres + Redis reachable via
DATABASE_URL/REDIS_URL (CI services, or `docker compose up -d` locally)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _test_settings_env() -> None:
    os.environ.setdefault("CORVEON_ENV", "test")
    os.environ.setdefault("LOG_FORMAT", "console")
    os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-production-use-32-bytes-min")
    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations(_test_settings_env: None) -> None:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def app():  # type: ignore[no-untyped-def]
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(app) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    yield
    async for session in app.state.db.session():
        await session.execute(text("TRUNCATE TABLE users, organizations RESTART IDENTITY CASCADE"))
        await session.commit()
        break
