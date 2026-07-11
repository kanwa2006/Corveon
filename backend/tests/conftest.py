"""Shared pytest fixtures. Requires a live Postgres + Redis reachable via
DATABASE_URL/REDIS_URL (CI services, or `docker compose up -d` locally)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
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
DEFAULT_PASSWORD = "correcthorsebattery"


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


@pytest_asyncio.fixture
async def auth_headers(
    client: AsyncClient,
) -> Callable[[str], Awaitable[dict[str, str]]]:
    """Registers + logs in a fresh user, returning an Authorization header dict."""

    async def _make(email: str) -> dict[str, str]:
        await client.post(
            "/api/v1/auth/register", json={"email": email, "password": DEFAULT_PASSWORD}
        )
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
        )
        token = response.json()["access"]
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(app) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    yield
    async for session in app.state.db.session():
        await session.execute(
            text(
                "TRUNCATE TABLE jobs, chunk_embeddings, document_chunks, documents, "
                "messages, chats, users, organizations RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
        break
    # Content-addressed caches (SSO discovery/JWKS, medication, evidence) key
    # solely on the request they cache, with no test-run isolation — a
    # literal issuer/URL reused across tests or process runs reads back a
    # stale entry from Redis, which nothing else here clears (unlike the
    # SQL tables truncated above).
    await app.state.redis.flushdb()
