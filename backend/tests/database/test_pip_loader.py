"""Beers 2023 + STOPP/START v3 pinned snapshot loader tests
(app/medication/pip_loader.py, ADR-0019).

The fixture CSV below is a small, explicitly synthetic subset chosen to
exercise the loader's row shape — not the actual licensed AGS Beers
Criteria 2023 / STOPP-START v3 tables, which are not bundled with this
repository (CLAUDE.md forbids fabricating medical facts even in test
data; these rows are structurally representative, not presented as real
citations)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from app.data.models.medication import FindingSeverity, PipCriterion, PipDirection, PipSource
from app.medication.pip_loader import PipCriteriaSnapshotError, load_pip_criteria_snapshot
from sqlalchemy import select

pytestmark = [pytest.mark.database]

_SAMPLE_CSV = (
    "source,criterion_id,drug_names,condition_keywords,direction,rationale,recommendation,"
    "severity\n"
    "beers_2023,TEST-B1,first_generation_antihistamine,,avoid,"
    "Anticholinergic burden increases fall and delirium risk.,"
    "Avoid; consider a non-anticholinergic alternative.,major\n"
    "stopp_v3,TEST-S1,nsaid,peptic ulcer,avoid,"
    "NSAIDs increase GI bleeding risk with a history of peptic ulcer disease.,"
    "Avoid; consider acetaminophen instead.,moderate\n"
    "start_v3,TEST-T1,bisphosphonate|calcium and vitamin d,osteoporosis,start_consider,"
    "Bone-protective therapy reduces fracture risk in osteoporosis.,"
    "Consider starting if not contraindicated.,moderate\n"
)


def _write_csv(tmp_path: Path, content: str = _SAMPLE_CSV) -> Path:
    path = tmp_path / "pip_sample.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_load_pip_criteria_snapshot_imports_rows_and_records_the_snapshot(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(tmp_path)
    version = f"test-{uuid.uuid4()}"

    async for session in app.state.db.session():
        snapshot = await load_pip_criteria_snapshot(
            session, path=path, source_label="test_pip_bundle", version=version
        )
        await session.commit()

        assert snapshot.row_count == 3
        assert snapshot.source == "test_pip_bundle"

        result = await session.execute(
            select(PipCriterion).where(PipCriterion.snapshot_id == snapshot.id)
        )
        rows = {row.criterion_id: row for row in result.scalars().all()}
        assert set(rows) == {"TEST-B1", "TEST-S1", "TEST-T1"}
        assert rows["TEST-B1"].source == PipSource.BEERS_2023
        assert rows["TEST-B1"].direction == PipDirection.AVOID
        assert rows["TEST-B1"].condition_keywords == []
        assert rows["TEST-T1"].source == PipSource.START_V3
        assert rows["TEST-T1"].direction == PipDirection.START_CONSIDER
        assert rows["TEST-T1"].drug_names == ["bisphosphonate", "calcium and vitamin d"]
        assert rows["TEST-T1"].severity == FindingSeverity.MODERATE
        break


@pytest.mark.asyncio
async def test_load_pip_criteria_snapshot_raises_on_checksum_mismatch(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(tmp_path)

    async for session in app.state.db.session():
        with pytest.raises(PipCriteriaSnapshotError, match="Checksum mismatch"):
            await load_pip_criteria_snapshot(
                session,
                path=path,
                source_label="test_pip_bundle",
                version="v1",
                expected_checksum="not-the-real-checksum",
            )
        break


@pytest.mark.asyncio
async def test_load_pip_criteria_snapshot_raises_when_file_is_missing(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    async for session in app.state.db.session():
        with pytest.raises(PipCriteriaSnapshotError, match="not found"):
            await load_pip_criteria_snapshot(
                session, path=tmp_path / "missing.csv", source_label="x", version="v1"
            )
        break


@pytest.mark.asyncio
async def test_load_pip_criteria_snapshot_raises_on_missing_required_columns(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(tmp_path, "source,criterion_id\nbeers_2023,TEST-B1\n")

    async for session in app.state.db.session():
        with pytest.raises(PipCriteriaSnapshotError, match="missing required columns"):
            await load_pip_criteria_snapshot(session, path=path, source_label="x", version="v1")
        break


@pytest.mark.asyncio
async def test_load_pip_criteria_snapshot_raises_on_unrecognized_source(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path,
        "source,criterion_id,drug_names,condition_keywords,direction,rationale,recommendation,"
        "severity\nmade_up_source,TEST-X1,drug,,avoid,Rationale.,Recommendation.,major\n",
    )

    async for session in app.state.db.session():
        with pytest.raises(PipCriteriaSnapshotError, match="Unrecognized source"):
            await load_pip_criteria_snapshot(session, path=path, source_label="x", version="v1")
        break


@pytest.mark.asyncio
async def test_load_pip_criteria_snapshot_raises_on_unrecognized_direction(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path,
        "source,criterion_id,drug_names,condition_keywords,direction,rationale,recommendation,"
        "severity\nbeers_2023,TEST-X2,drug,,maybe,Rationale.,Recommendation.,major\n",
    )

    async for session in app.state.db.session():
        with pytest.raises(PipCriteriaSnapshotError, match="Unrecognized direction"):
            await load_pip_criteria_snapshot(session, path=path, source_label="x", version="v1")
        break


@pytest.mark.asyncio
async def test_load_pip_criteria_snapshot_raises_on_empty_drug_names(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = _write_csv(
        tmp_path,
        "source,criterion_id,drug_names,condition_keywords,direction,rationale,recommendation,"
        "severity\nbeers_2023,TEST-X3,,,avoid,Rationale.,Recommendation.,major\n",
    )

    async for session in app.state.db.session():
        with pytest.raises(PipCriteriaSnapshotError, match="no drug_names"):
            await load_pip_criteria_snapshot(session, path=path, source_label="x", version="v1")
        break
