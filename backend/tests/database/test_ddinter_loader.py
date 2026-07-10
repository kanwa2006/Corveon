"""DDInter 2.0 pinned snapshot loader tests (app/medication/ddinter_loader.py).

The fixture CSV below is a small, explicitly synthetic subset of real,
well-established textbook drug-drug interactions (not the actual licensed
DDInter 2.0 export, which is not bundled with this repository) — chosen
because CLAUDE.md forbids fabricating medical facts even in test data."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from app.data.models.medication import DrugInteraction
from app.medication.ddinter_loader import (
    DDInterSnapshotError,
    compute_checksum,
    load_ddinter_snapshot,
)
from sqlalchemy import select

pytestmark = [pytest.mark.database]

_SAMPLE_CSV = """drug_a,drug_b,severity,description
warfarin,aspirin,major,Combining anticoagulants and antiplatelets increases bleeding risk.
lisinopril,potassium chloride,moderate,ACE inhibitors plus potassium supplements risk hyperkalemia.
metformin,propranolol,minor,Non-selective beta blockers may mask hypoglycemia symptoms.
"""


def _write_csv(tmp_path: Path, content: str = _SAMPLE_CSV) -> Path:
    path = tmp_path / "ddinter_sample.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_load_ddinter_snapshot_imports_rows_and_records_the_snapshot(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(tmp_path)
    version = f"test-{uuid.uuid4()}"

    async for session in app.state.db.session():
        snapshot = await load_ddinter_snapshot(session, path=path, version=version)
        await session.commit()

        assert snapshot.row_count == 3
        assert snapshot.source == "ddinter"
        assert snapshot.checksum == compute_checksum(path)

        result = await session.execute(
            select(DrugInteraction).where(DrugInteraction.snapshot_id == snapshot.id)
        )
        rows = result.scalars().all()
        assert len(rows) == 3
        break


@pytest.mark.asyncio
async def test_load_ddinter_snapshot_normalizes_and_sorts_drug_name_pairs(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    # "Warfarin"/"Aspirin" (mixed case) should normalize to the same sorted
    # pair as a lookup for "aspirin"/"warfarin" would use.
    path = _write_csv(
        tmp_path,
        "drug_a,drug_b,severity,description\nWarfarin,  Aspirin ,major,Increased bleeding risk.\n",
    )
    version = f"test-{uuid.uuid4()}"

    async for session in app.state.db.session():
        snapshot = await load_ddinter_snapshot(session, path=path, version=version)
        await session.commit()

        result = await session.execute(
            select(DrugInteraction).where(DrugInteraction.snapshot_id == snapshot.id)
        )
        row = result.scalar_one()
        assert (row.drug_a_name, row.drug_b_name) == ("aspirin", "warfarin")
        break


@pytest.mark.asyncio
async def test_load_ddinter_snapshot_raises_on_checksum_mismatch(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(tmp_path)

    async for session in app.state.db.session():
        with pytest.raises(DDInterSnapshotError, match="Checksum mismatch"):
            await load_ddinter_snapshot(
                session, path=path, version="v1", expected_checksum="not-the-real-checksum"
            )
        break


@pytest.mark.asyncio
async def test_load_ddinter_snapshot_raises_when_file_is_missing(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    async for session in app.state.db.session():
        with pytest.raises(DDInterSnapshotError, match="not found"):
            await load_ddinter_snapshot(session, path=tmp_path / "missing.csv", version="v1")
        break


@pytest.mark.asyncio
async def test_load_ddinter_snapshot_raises_on_missing_required_columns(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(tmp_path, "drug_a,drug_b\nwarfarin,aspirin\n")

    async for session in app.state.db.session():
        with pytest.raises(DDInterSnapshotError, match="missing required columns"):
            await load_ddinter_snapshot(session, path=path, version="v1")
        break


@pytest.mark.asyncio
async def test_load_ddinter_snapshot_raises_on_unrecognized_severity(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path,
        "drug_a,drug_b,severity,description\nwarfarin,aspirin,catastrophic,Made up severity.\n",
    )

    async for session in app.state.db.session():
        with pytest.raises(DDInterSnapshotError, match="Unrecognized severity"):
            await load_ddinter_snapshot(session, path=path, version="v1")
        break
