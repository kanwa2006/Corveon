"""Golden tests for the DDI rules engine (app/medication/interactions.py) —
deterministic outputs against a real, pinned DDInter snapshot loaded via
app/medication/ddinter_loader.py (blueprint §7's medication-safety testing
requirement: "pytest with pinned DDInter/Beers/STOPP-START snapshots ...
deterministic rule outputs"), plus a fake openFDA client for the fallback
path (no live network in tests)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from app.data.models.medication import FindingSeverity, InteractionSource
from app.medication.ddinter_loader import load_ddinter_snapshot
from app.medication.interactions import NormalizedMedication, find_interactions
from app.medication.openfda_ddi_client import OpenFdaDdiMatch

pytestmark = [pytest.mark.database, pytest.mark.golden]

_SAMPLE_CSV = """drug_a,drug_b,severity,description
warfarin,aspirin,major,Combining anticoagulants and antiplatelets increases bleeding risk.
lisinopril,potassium chloride,moderate,ACE inhibitors plus potassium supplements risk hyperkalemia.
"""


def _medication(name: str) -> NormalizedMedication:
    return NormalizedMedication(
        raw_text=name, name=name, rxcui=None, dose=None, route=None, frequency=None
    )


class _FakeOpenFdaDdiClient:
    def __init__(self, match: OpenFdaDdiMatch | None = None) -> None:
        self._match = match
        self.calls: list[tuple[str, str]] = []

    async def check_pair(self, label_drug: str, mentioned_drug: str) -> OpenFdaDdiMatch | None:
        self.calls.append((label_drug, mentioned_drug))
        return self._match


@pytest.mark.asyncio
async def test_find_interactions_matches_a_pinned_ddinter_pair_regardless_of_order(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(_SAMPLE_CSV, encoding="utf-8")

    async for session in app.state.db.session():
        await load_ddinter_snapshot(session, path=path, version=f"test-{uuid.uuid4()}")
        await session.commit()

        # Input order is the reverse of the CSV's (aspirin, warfarin) — the
        # engine must still find it via sorted-pair lookup.
        medications = [_medication("aspirin"), _medication("warfarin")]
        findings = await find_interactions(
            medications, session=session, openfda_client=_FakeOpenFdaDdiClient()
        )

        assert len(findings) == 1
        finding = findings[0]
        assert finding.medication_a_index == 0
        assert finding.medication_b_index == 1
        assert finding.severity == FindingSeverity.MAJOR
        assert finding.source == InteractionSource.DDINTER
        assert "bleeding" in finding.explanation.lower()
        break


@pytest.mark.asyncio
async def test_find_interactions_is_case_insensitive_on_drug_names(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(_SAMPLE_CSV, encoding="utf-8")

    async for session in app.state.db.session():
        await load_ddinter_snapshot(session, path=path, version=f"test-{uuid.uuid4()}")
        await session.commit()

        medications = [_medication("Lisinopril"), _medication("POTASSIUM CHLORIDE")]
        findings = await find_interactions(
            medications, session=session, openfda_client=_FakeOpenFdaDdiClient()
        )

        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.MODERATE
        break


@pytest.mark.asyncio
async def test_find_interactions_matches_via_ingredient_match_names_not_branded_display_names(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    """Regression (N1): DDInter rows key on ingredient names — a medication
    whose display name is RxNav's verbose branded canonical string must
    still match via its ingredient match_names."""
    path = tmp_path / "sample.csv"
    path.write_text(_SAMPLE_CSV, encoding="utf-8")

    async for session in app.state.db.session():
        await load_ddinter_snapshot(session, path=path, version=f"test-{uuid.uuid4()}")
        await session.commit()

        medications = [
            NormalizedMedication(
                raw_text="Coumadin 1mg",
                name="warfarin sodium 1 MG Oral Tablet [Coumadin]",
                rxcui="855290",
                dose="1mg",
                route=None,
                frequency=None,
                match_names=("warfarin", "coumadin"),
            ),
            NormalizedMedication(
                raw_text="aspirin 81mg",
                name="aspirin 81 MG Oral Tablet",
                rxcui="243670",
                dose="81mg",
                route=None,
                frequency=None,
                match_names=("aspirin",),
            ),
        ]
        findings = await find_interactions(
            medications, session=session, openfda_client=_FakeOpenFdaDdiClient()
        )

        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.MAJOR
        assert findings[0].source == InteractionSource.DDINTER
        break


@pytest.mark.asyncio
async def test_find_interactions_falls_back_to_openfda_when_ddinter_has_no_record(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(_SAMPLE_CSV, encoding="utf-8")

    async for session in app.state.db.session():
        await load_ddinter_snapshot(session, path=path, version=f"test-{uuid.uuid4()}")
        await session.commit()

        fake_match = OpenFdaDdiMatch(
            label_id="label-1",
            url="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=label-1",
            snippet="Some label text mentioning the other drug.",
        )
        # drug_data_snapshots/drug_interactions are shared reference data,
        # not truncated between tests (unlike chat-scoped tables) — use
        # unique names so no other test's leftover snapshot row can
        # accidentally give DDInter a real match here.
        medications = [
            _medication(f"drug-a-{uuid.uuid4()}"),
            _medication(f"drug-b-{uuid.uuid4()}"),
        ]
        findings = await find_interactions(
            medications, session=session, openfda_client=_FakeOpenFdaDdiClient(fake_match)
        )

        assert len(findings) == 1
        assert findings[0].source == InteractionSource.OPENFDA_LABEL
        assert findings[0].severity == FindingSeverity.UNCLASSIFIED
        assert findings[0].rule_id == "label-1"
        break


@pytest.mark.asyncio
async def test_find_interactions_returns_empty_when_neither_source_has_a_record(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(_SAMPLE_CSV, encoding="utf-8")

    async for session in app.state.db.session():
        await load_ddinter_snapshot(session, path=path, version=f"test-{uuid.uuid4()}")
        await session.commit()

        medications = [
            _medication(f"drug-c-{uuid.uuid4()}"),
            _medication(f"drug-d-{uuid.uuid4()}"),
        ]
        findings = await find_interactions(
            medications, session=session, openfda_client=_FakeOpenFdaDdiClient(None)
        )

        assert findings == []
        break


@pytest.mark.asyncio
async def test_find_interactions_checks_every_distinct_pair(
    app,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(_SAMPLE_CSV, encoding="utf-8")

    async for session in app.state.db.session():
        await load_ddinter_snapshot(session, path=path, version=f"test-{uuid.uuid4()}")
        await session.commit()

        # 3 medications -> 3 pairs; only (warfarin, aspirin) matches.
        medications = [_medication("warfarin"), _medication("aspirin"), _medication("metformin")]
        findings = await find_interactions(
            medications, session=session, openfda_client=_FakeOpenFdaDdiClient(None)
        )

        assert len(findings) == 1
        assert {findings[0].medication_a_index, findings[0].medication_b_index} == {0, 1}
        break
