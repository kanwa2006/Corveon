"""Unit test for the ARQ worker entrypoint (app/workers/main.py) — this
module is only otherwise exercised by actually running
`arq app.workers.main.WorkerSettings` in production, never in CI."""

from __future__ import annotations

import pytest
from app.workers.main import WorkerSettings, on_shutdown, on_startup
from app.workers.tasks import ingest_document

pytestmark = pytest.mark.unit


def test_worker_settings_registers_ingest_document() -> None:
    assert WorkerSettings.functions == [ingest_document]


def test_worker_settings_has_redis_settings_from_env() -> None:
    assert WorkerSettings.redis_settings is not None


@pytest.mark.asyncio
async def test_on_startup_populates_ctx_with_expected_keys() -> None:
    ctx: dict[str, object] = {}
    await on_startup(ctx)
    try:
        assert {"settings", "db", "storage", "embedding_model"} <= ctx.keys()
    finally:
        await on_shutdown(ctx)
