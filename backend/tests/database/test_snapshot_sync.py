"""Tests for automated, idempotent pinned-snapshot sync
(app/medication/snapshot_sync.py) — wires the `*_SNAPSHOT_PATH`/
`*_SNAPSHOT_VERSION` settings to the existing DDInter/PIP loaders."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.data.models.medication import DrugDataSnapshot
from app.medication.snapshot_sync import (
    SnapshotConfigurationError,
    sync_all_pinned_snapshots,
)
from sqlalchemy import select

pytestmark = [pytest.mark.database]

_DDINTER_CSV = """drug_a,drug_b,severity,description
warfarin,aspirin,major,Combining anticoagulants and antiplatelets increases bleeding risk.
"""

_PIP_CSV = (
    "source,criterion_id,drug_names,condition_keywords,direction,rationale,recommendation,"
    "severity\n"
    "beers_2023,SYNC-TEST-1,first_generation_antihistamine,,avoid,"
    "Anticholinergic burden increases fall risk.,Avoid; consider an alternative.,major\n"
)


def _settings(**overrides: object) -> Settings:
    return Settings(
        JWT_SECRET_KEY="a-real-generated-secret-not-a-placeholder-value",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        _env_file=None,  # type: ignore[call-arg]
        **overrides,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_sync_reports_not_configured_when_no_paths_are_set(
    app,  # type: ignore[no-untyped-def]
) -> None:
    async for session in app.state.db.session():
        results = await sync_all_pinned_snapshots(session, _settings())
        await session.commit()

        assert {r.source_label: r.action for r in results} == {
            "ddinter": "not_configured",
            "beers_2023": "not_configured",
            "stopp_start_v3": "not_configured",
        }
        break


@pytest.mark.asyncio
async def test_sync_imports_ddinter_when_configured_and_is_idempotent(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = tmp_path / "ddinter_sync_sample.csv"
    path.write_text(_DDINTER_CSV, encoding="utf-8")
    settings = _settings(
        DDINTER_SNAPSHOT_PATH=str(path), DDINTER_SNAPSHOT_VERSION="sync-test-2025-01"
    )

    async for session in app.state.db.session():
        first = await sync_all_pinned_snapshots(session, settings)
        await session.commit()

        ddinter_result = next(r for r in first if r.source_label == "ddinter")
        assert ddinter_result.action == "imported"
        assert ddinter_result.row_count == 1
        assert ddinter_result.version == "sync-test-2025-01"

        second = await sync_all_pinned_snapshots(session, settings)
        await session.commit()
        assert next(r for r in second if r.source_label == "ddinter").action == "already_current"

        count = await session.execute(
            select(DrugDataSnapshot).where(
                DrugDataSnapshot.source == "ddinter",
                DrugDataSnapshot.version == "sync-test-2025-01",
            )
        )
        assert len(count.scalars().all()) == 1
        break


@pytest.mark.asyncio
async def test_sync_imports_a_pip_source_when_configured(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = tmp_path / "pip_sync_sample.csv"
    path.write_text(_PIP_CSV, encoding="utf-8")
    settings = _settings(
        BEERS_2023_SNAPSHOT_PATH=str(path), BEERS_2023_SNAPSHOT_VERSION="sync-test-2023"
    )

    async for session in app.state.db.session():
        results = await sync_all_pinned_snapshots(session, settings)
        await session.commit()

        beers_result = next(r for r in results if r.source_label == "beers_2023")
        assert beers_result.action == "imported"
        assert beers_result.row_count == 1
        break


@pytest.mark.asyncio
async def test_sync_raises_configuration_error_when_ddinter_version_is_missing(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = tmp_path / "ddinter_missing_version.csv"
    path.write_text(_DDINTER_CSV, encoding="utf-8")
    settings = _settings(DDINTER_SNAPSHOT_PATH=str(path))

    async for session in app.state.db.session():
        with pytest.raises(SnapshotConfigurationError, match="DDINTER_SNAPSHOT_VERSION"):
            await sync_all_pinned_snapshots(session, settings)
        break


@pytest.mark.asyncio
async def test_sync_raises_configuration_error_when_a_pip_source_version_is_missing(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = tmp_path / "pip_missing_version.csv"
    path.write_text(_PIP_CSV, encoding="utf-8")
    settings = _settings(STOPP_START_V3_SNAPSHOT_PATH=str(path))

    async for session in app.state.db.session():
        with pytest.raises(SnapshotConfigurationError, match="stopp_start_v3"):
            await sync_all_pinned_snapshots(session, settings)
        break
