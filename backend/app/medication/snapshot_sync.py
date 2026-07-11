"""Automated, idempotent sync of every pinned drug-data snapshot source
from operator-configured local paths (blueprint §10.4: drug data "is
imported as pinned, checksummed snapshots ... so results are reproducible
and auditable across time"). Wires the `*_SNAPSHOT_PATH`/`*_SNAPSHOT_VERSION`
settings (`app/core/config.py`) — previously declared but never read by any
import logic — to the existing per-source loaders
(`ddinter_loader.py`, `pip_loader.py`), so an operator (or a scheduled
worker run, `app/workers/tasks.py::sync_pinned_snapshots`) has one
reproducible sync step instead of separately invoking each loader's CLI by
hand with a manually re-typed version each time.

Running this repeatedly is always safe: a source already imported at its
pinned version+checksum is left untouched, never re-imported or
duplicated — the same "fails loudly, never silently wrong" posture the
underlying loaders already have (data/loaders/README.md)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.data.models.medication import DrugDataSnapshot
from app.medication.ddinter_loader import compute_checksum, load_ddinter_snapshot
from app.medication.pip_loader import load_pip_criteria_snapshot

SyncAction = Literal["imported", "already_current", "not_configured"]


class SnapshotConfigurationError(Exception):
    """Raised when a snapshot path is configured but its paired version
    setting isn't — a reproducible import needs an explicit, reviewed
    version label, never one inferred from file content or mtime
    (CLAUDE.md: never silently ingest possibly-wrong medical data)."""


@dataclass(frozen=True, slots=True)
class SnapshotSyncResult:
    source_label: str
    action: SyncAction
    version: str | None = None
    row_count: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_label": self.source_label,
            "action": self.action,
            "version": self.version,
            "row_count": self.row_count,
        }


async def _already_current(
    session: AsyncSession, *, source: str, version: str, checksum: str
) -> bool:
    result = await session.execute(
        select(DrugDataSnapshot.id).where(
            DrugDataSnapshot.source == source,
            DrugDataSnapshot.version == version,
            DrugDataSnapshot.checksum == checksum,
        )
    )
    return result.scalar_one_or_none() is not None


async def _sync_ddinter(session: AsyncSession, settings: Settings) -> SnapshotSyncResult:
    if not settings.DDINTER_SNAPSHOT_PATH:
        return SnapshotSyncResult(source_label="ddinter", action="not_configured")
    if not settings.DDINTER_SNAPSHOT_VERSION:
        raise SnapshotConfigurationError(
            "DDINTER_SNAPSHOT_PATH is set but DDINTER_SNAPSHOT_VERSION is not."
        )

    path = Path(settings.DDINTER_SNAPSHOT_PATH)
    checksum = await asyncio.to_thread(compute_checksum, path)
    if await _already_current(
        session, source="ddinter", version=settings.DDINTER_SNAPSHOT_VERSION, checksum=checksum
    ):
        return SnapshotSyncResult(
            source_label="ddinter",
            action="already_current",
            version=settings.DDINTER_SNAPSHOT_VERSION,
        )

    snapshot = await load_ddinter_snapshot(
        session, path=path, version=settings.DDINTER_SNAPSHOT_VERSION, expected_checksum=checksum
    )
    return SnapshotSyncResult(
        source_label="ddinter",
        action="imported",
        version=snapshot.version,
        row_count=snapshot.row_count,
    )


async def _sync_pip_source(
    session: AsyncSession, *, source_label: str, path_str: str | None, version: str | None
) -> SnapshotSyncResult:
    if not path_str:
        return SnapshotSyncResult(source_label=source_label, action="not_configured")
    if not version:
        raise SnapshotConfigurationError(
            f"{source_label} snapshot path is set but its paired version setting is not."
        )

    path = Path(path_str)
    checksum = await asyncio.to_thread(compute_checksum, path)
    if await _already_current(session, source=source_label, version=version, checksum=checksum):
        return SnapshotSyncResult(
            source_label=source_label, action="already_current", version=version
        )

    snapshot = await load_pip_criteria_snapshot(
        session,
        path=path,
        source_label=source_label,
        version=version,
        expected_checksum=checksum,
    )
    return SnapshotSyncResult(
        source_label=source_label,
        action="imported",
        version=snapshot.version,
        row_count=snapshot.row_count,
    )


async def sync_all_pinned_snapshots(
    session: AsyncSession, settings: Settings
) -> list[SnapshotSyncResult]:
    """Syncs every pinned snapshot source this deployment has configured a
    local path for — DDInter 2.0, Beers 2023, STOPP/START v3. A source
    with no configured path is reported ``not_configured`` (an absence,
    not a failure — same posture as an unconfigured AI provider, §23.1);
    a source whose file's checksum already matches an existing
    ``DrugDataSnapshot`` row is reported ``already_current`` and is not
    re-imported. Raises ``SnapshotConfigurationError`` if any configured
    path is missing its paired version setting — a partial configuration
    is a loud error, not a silently skipped source."""
    return [
        await _sync_ddinter(session, settings),
        await _sync_pip_source(
            session,
            source_label="beers_2023",
            path_str=settings.BEERS_2023_SNAPSHOT_PATH,
            version=settings.BEERS_2023_SNAPSHOT_VERSION,
        ),
        await _sync_pip_source(
            session,
            source_label="stopp_start_v3",
            path_str=settings.STOPP_START_V3_SNAPSHOT_PATH,
            version=settings.STOPP_START_V3_SNAPSHOT_VERSION,
        ),
    ]


async def _main() -> None:
    from app.core.config import get_settings
    from app.data.base import Database

    settings = get_settings()
    db = Database(settings)
    try:
        async for session in db.session():
            results = await sync_all_pinned_snapshots(session, settings)
            await session.commit()
            for result in results:
                print(
                    f"{result.source_label}: {result.action}"
                    + (
                        f" (version={result.version}, rows={result.row_count})"
                        if result.version
                        else ""
                    )
                )
            break
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
