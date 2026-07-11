"""Golden tests for PIP screening (app/medication/pip_screening.py,
ADR-0019) — deterministic outputs against directly-seeded ``pip_criteria``
rows (blueprint §7's medication-safety testing requirement: "pytest with
pinned DDInter/Beers/STOPP-START snapshots ... deterministic rule
outputs")."""

from __future__ import annotations

import uuid

import pytest
from app.data.models.medication import (
    DrugDataSnapshot,
    FindingSeverity,
    PipCriterion,
    PipDirection,
    PipSource,
)
from app.medication.interactions import NormalizedMedication
from app.medication.pip_screening import check_pip_criteria

pytestmark = [pytest.mark.database, pytest.mark.golden]


def _medication(name: str) -> NormalizedMedication:
    return NormalizedMedication(
        raw_text=name, name=name, rxcui=None, dose=None, route=None, frequency=None
    )


async def _seed_criterion(
    session,  # type: ignore[no-untyped-def]
    *,
    source: PipSource,
    criterion_id: str,
    drug_names: list[str],
    condition_keywords: list[str],
    direction: PipDirection,
    severity: FindingSeverity = FindingSeverity.MODERATE,
) -> None:
    snapshot = DrugDataSnapshot(
        source=source.value, version=f"test-{uuid.uuid4()}", checksum="test", row_count=1
    )
    session.add(snapshot)
    await session.flush()
    session.add(
        PipCriterion(
            snapshot_id=snapshot.id,
            source=source,
            criterion_id=criterion_id,
            drug_names=drug_names,
            condition_keywords=condition_keywords,
            direction=direction,
            rationale="Test rationale.",
            recommendation="Test recommendation.",
            severity=severity,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_check_pip_criteria_flags_an_unconditional_beers_avoid_match(
    app,  # type: ignore[no-untyped-def]
) -> None:
    drug = f"beers-drug-{uuid.uuid4()}"
    async for session in app.state.db.session():
        await _seed_criterion(
            session,
            source=PipSource.BEERS_2023,
            criterion_id="TEST-BEERS-1",
            drug_names=[drug],
            condition_keywords=[],
            direction=PipDirection.AVOID,
            severity=FindingSeverity.MAJOR,
        )
        await session.commit()

        findings = await check_pip_criteria(
            [_medication(drug)], age_years=70, conditions=[], session=session
        )

        assert len(findings) == 1
        finding = findings[0]
        assert finding.medication_index == 0
        assert finding.source == PipSource.BEERS_2023
        assert finding.direction == PipDirection.AVOID
        assert finding.severity == FindingSeverity.MAJOR
        assert finding.matched_condition is None
        assert finding.rule_id == "beers_2023:TEST-BEERS-1"
        break


@pytest.mark.asyncio
async def test_check_pip_criteria_requires_a_matching_condition_for_stopp(
    app,  # type: ignore[no-untyped-def]
) -> None:
    drug = f"stopp-drug-{uuid.uuid4()}"
    async for session in app.state.db.session():
        await _seed_criterion(
            session,
            source=PipSource.STOPP_V3,
            criterion_id="TEST-STOPP-1",
            drug_names=[drug],
            condition_keywords=["heart failure"],
            direction=PipDirection.AVOID,
        )
        await session.commit()

        no_match = await check_pip_criteria(
            [_medication(drug)], age_years=70, conditions=["diabetes"], session=session
        )
        assert no_match == []

        match = await check_pip_criteria(
            [_medication(drug)],
            age_years=70,
            conditions=["chronic heart failure"],
            session=session,
        )
        assert len(match) == 1
        assert match[0].matched_condition == "chronic heart failure"
        break


@pytest.mark.asyncio
async def test_check_pip_criteria_start_fires_on_omission(
    app,  # type: ignore[no-untyped-def]
) -> None:
    drug = f"start-drug-{uuid.uuid4()}"
    # pip_criteria is shared reference data, not truncated between tests
    # (like drug_interactions) — a unique condition keyword, not just a
    # unique drug name, is required for a START criterion: it fires on
    # *absence*, so a condition shared with another test's criterion would
    # spuriously match here too.
    condition = f"osteoporosis-{uuid.uuid4()}"
    async for session in app.state.db.session():
        await _seed_criterion(
            session,
            source=PipSource.START_V3,
            criterion_id="TEST-START-1",
            drug_names=[drug],
            condition_keywords=[condition],
            direction=PipDirection.START_CONSIDER,
        )
        await session.commit()

        other_drug = f"unrelated-{uuid.uuid4()}"
        findings = await check_pip_criteria(
            [_medication(other_drug)],
            age_years=70,
            conditions=[condition],
            session=session,
        )

        assert len(findings) == 1
        finding = findings[0]
        assert finding.medication_index is None
        assert finding.direction == PipDirection.START_CONSIDER
        assert finding.drug_names == [drug]
        break


@pytest.mark.asyncio
async def test_check_pip_criteria_start_does_not_fire_when_drug_already_present(
    app,  # type: ignore[no-untyped-def]
) -> None:
    drug = f"start-present-{uuid.uuid4()}"
    condition = f"osteoporosis-{uuid.uuid4()}"
    async for session in app.state.db.session():
        await _seed_criterion(
            session,
            source=PipSource.START_V3,
            criterion_id="TEST-START-2",
            drug_names=[drug],
            condition_keywords=[condition],
            direction=PipDirection.START_CONSIDER,
        )
        await session.commit()

        findings = await check_pip_criteria(
            [_medication(drug)], age_years=70, conditions=[condition], session=session
        )

        assert findings == []
        break


@pytest.mark.asyncio
async def test_check_pip_criteria_skips_screening_below_age_65(
    app,  # type: ignore[no-untyped-def]
) -> None:
    drug = f"young-patient-drug-{uuid.uuid4()}"
    async for session in app.state.db.session():
        await _seed_criterion(
            session,
            source=PipSource.BEERS_2023,
            criterion_id="TEST-BEERS-2",
            drug_names=[drug],
            condition_keywords=[],
            direction=PipDirection.AVOID,
        )
        await session.commit()

        findings = await check_pip_criteria(
            [_medication(drug)], age_years=64, conditions=[], session=session
        )

        assert findings == []
        break


@pytest.mark.asyncio
async def test_check_pip_criteria_is_case_insensitive_on_drug_and_condition(
    app,  # type: ignore[no-untyped-def]
) -> None:
    drug = f"Case-Drug-{uuid.uuid4()}"
    async for session in app.state.db.session():
        await _seed_criterion(
            session,
            source=PipSource.STOPP_V3,
            criterion_id="TEST-STOPP-2",
            drug_names=[drug.lower()],
            condition_keywords=["renal impairment"],
            direction=PipDirection.AVOID,
        )
        await session.commit()

        findings = await check_pip_criteria(
            [_medication(drug.upper())],
            age_years=80,
            conditions=["Severe RENAL Impairment"],
            session=session,
        )

        assert len(findings) == 1
        break
