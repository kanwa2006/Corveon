"""Database tests: migration up/down round-trip (ADR-0002)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _alembic_config() -> Config:
    return Config(str(_BACKEND_ROOT / "alembic.ini"))


@pytest.mark.database
def test_migration_round_trip_restores_schema(_apply_migrations: None) -> None:
    cfg = _alembic_config()

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    # A fresh autogenerate against head must be an empty diff (ADR-0002) — this
    # test only re-confirms the round trip runs cleanly; the CI sync-check step
    # verifies the empty-diff property directly.


@pytest.mark.database
@pytest.mark.asyncio
async def test_baseline_tables_exist() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
    finally:
        await engine.dispose()

    assert "organizations" in table_names
    assert "users" in table_names


@pytest.mark.database
@pytest.mark.asyncio
async def test_users_email_is_unique_indexed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            indexes = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_indexes("users"))
    finally:
        await engine.dispose()

    email_indexes = [ix for ix in indexes if ix["column_names"] == ["email"]]
    assert email_indexes, "expected an index on users.email"
    assert email_indexes[0]["unique"] is True
