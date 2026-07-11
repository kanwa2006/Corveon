"""Golden tests for medication-discrepancy classification
(app/medication/discrepancy.py, ADR-0019) — pure, deterministic, no
database required."""

from __future__ import annotations

import pytest
from app.medication.discrepancy import classify_discrepancies
from app.medication.interactions import NormalizedMedication

pytestmark = pytest.mark.unit


def _med(
    name: str,
    *,
    rxcui: str | None = None,
    dose: str | None = None,
    frequency: str | None = None,
) -> NormalizedMedication:
    return NormalizedMedication(
        raw_text=name, name=name, rxcui=rxcui, dose=dose, route=None, frequency=frequency
    )


def test_classify_discrepancies_flags_an_added_medication() -> None:
    previous = [_med("metformin")]
    current = [_med("metformin"), _med("lisinopril")]

    findings = classify_discrepancies(previous, current)

    assert len(findings) == 1
    assert findings[0].kind == "added"
    assert findings[0].current_index == 1
    assert findings[0].previous_index is None


def test_classify_discrepancies_flags_an_omitted_medication() -> None:
    previous = [_med("metformin"), _med("lisinopril")]
    current = [_med("metformin")]

    findings = classify_discrepancies(previous, current)

    assert len(findings) == 1
    assert findings[0].kind == "omitted"
    assert findings[0].previous_index == 1
    assert findings[0].current_index is None


def test_classify_discrepancies_flags_a_dose_change() -> None:
    previous = [_med("metformin", dose="500mg")]
    current = [_med("metformin", dose="1000mg")]

    findings = classify_discrepancies(previous, current)

    assert len(findings) == 1
    assert findings[0].kind == "dose_changed"
    assert findings[0].provenance["previous_dose"] == "500mg"
    assert findings[0].provenance["current_dose"] == "1000mg"


def test_classify_discrepancies_flags_a_frequency_change() -> None:
    previous = [_med("metformin", frequency="once daily")]
    current = [_med("metformin", frequency="twice daily")]

    findings = classify_discrepancies(previous, current)

    assert len(findings) == 1
    assert findings[0].kind == "frequency_changed"


def test_classify_discrepancies_reports_nothing_for_an_unchanged_medication() -> None:
    previous = [_med("metformin", dose="500mg", frequency="twice daily")]
    current = [_med("metformin", dose="500mg", frequency="twice daily")]

    assert classify_discrepancies(previous, current) == []


def test_classify_discrepancies_matches_by_rxcui_even_if_the_name_text_differs() -> None:
    # Same drug, differently transcribed each time — RxCUI-level matching
    # (blueprint §9) must still pair them rather than reporting a spurious
    # add+omit.
    previous = [_med("metformin hcl", rxcui="6809", dose="500mg")]
    current = [_med("Metformin", rxcui="6809", dose="1000mg")]

    findings = classify_discrepancies(previous, current)

    assert len(findings) == 1
    assert findings[0].kind == "dose_changed"


def test_classify_discrepancies_falls_back_to_name_when_rxcui_is_missing() -> None:
    previous = [_med("aspirin", rxcui=None, dose="81mg")]
    current = [_med("Aspirin", rxcui=None, dose="325mg")]

    findings = classify_discrepancies(previous, current)

    assert len(findings) == 1
    assert findings[0].kind == "dose_changed"


def test_classify_discrepancies_handles_duplicate_entries_by_list_order() -> None:
    previous = [_med("aspirin", dose="81mg"), _med("aspirin", dose="325mg")]
    current = [_med("aspirin", dose="81mg")]

    findings = classify_discrepancies(previous, current)

    # First occurrence pairs (no change); the second is unmatched -> omitted.
    assert len(findings) == 1
    assert findings[0].kind == "omitted"
    assert findings[0].previous_index == 1
