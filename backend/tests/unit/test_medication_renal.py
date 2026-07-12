"""Unit/golden tests for app/medication/renal.py (blueprint §9, ADR-0005) —
deterministic Cockcroft-Gault CrCl and 2021 race-free CKD-EPI eGFR
(de-indexed to BSA), and the threshold/divergence rules built on top.

Reference values for the two equations were independently cross-checked
against the NKF/ASN CKD-EPI 2021 online calculator and standard
Cockcroft-Gault worked examples before being pinned here as golden values —
these are not just "whatever the code currently outputs"."""

from __future__ import annotations

import pytest
from app.data.models.medication import FindingSeverity
from app.medication.interactions import NormalizedMedication
from app.medication.renal import (
    RenalParameters,
    check_renal_thresholds,
    ckd_epi_2021_egfr,
    cockcroft_gault_crcl,
)

pytestmark = pytest.mark.unit


def _medication(name: str) -> NormalizedMedication:
    return NormalizedMedication(
        raw_text=name, name=name, rxcui=None, dose=None, route=None, frequency=None
    )


class TestCockcroftGaultCrcl:
    def test_male_reference_case(self) -> None:
        # 65yo male, 70kg, Scr=1.2 mg/dL -> a standard textbook CrCl example.
        params = RenalParameters(
            age_years=65, weight_kg=70, sex="male", serum_creatinine_mg_dl=1.2, height_cm=175
        )
        assert cockcroft_gault_crcl(params) == pytest.approx(60.8, abs=0.1)

    def test_female_reference_case_applies_the_0_85_factor(self) -> None:
        # 60yo female, 60kg, Scr=0.9 mg/dL.
        params = RenalParameters(
            age_years=60, weight_kg=60, sex="female", serum_creatinine_mg_dl=0.9, height_cm=160
        )
        assert cockcroft_gault_crcl(params) == pytest.approx(62.96, abs=0.1)


class TestCkdEpi2021Egfr:
    def test_male_reference_case_deindexed_to_bsa(self) -> None:
        # 50yo male, Scr=1.0 mg/dL -> indexed eGFR ~91.7 mL/min/1.73m^2
        # (NKF/ASN reference); de-indexed to this patient's own BSA
        # (170cm/70kg, ~1.81 m^2) per ADR-0005.
        params = RenalParameters(
            age_years=50, weight_kg=70, sex="male", serum_creatinine_mg_dl=1.0, height_cm=170
        )
        assert ckd_epi_2021_egfr(params) == pytest.approx(95.9, abs=0.2)

    def test_female_reference_case_applies_the_1_012_factor(self) -> None:
        params = RenalParameters(
            age_years=60, weight_kg=60, sex="female", serum_creatinine_mg_dl=0.9, height_cm=160
        )
        assert ckd_epi_2021_egfr(params) == pytest.approx(68.62, abs=0.2)


class TestCheckRenalThresholds:
    def test_no_finding_for_a_non_threshold_sensitive_drug(self) -> None:
        # Even with severely impaired renal function, metformin isn't on
        # the threshold-sensitive list — no finding.
        params = RenalParameters(
            age_years=85, weight_kg=50, sex="male", serum_creatinine_mg_dl=3.0, height_cm=170
        )
        findings = check_renal_thresholds([_medication("metformin")], params)
        assert findings == []

    def test_no_finding_when_both_equations_agree_renal_function_is_normal(self) -> None:
        params = RenalParameters(
            age_years=30, weight_kg=75, sex="male", serum_creatinine_mg_dl=0.8, height_cm=180
        )
        findings = check_renal_thresholds([_medication("apixaban")], params)
        assert findings == []

    def test_major_finding_when_both_equations_agree_renal_function_is_impaired(self) -> None:
        params = RenalParameters(
            age_years=85, weight_kg=50, sex="male", serum_creatinine_mg_dl=3.0, height_cm=170
        )
        findings = check_renal_thresholds([_medication("apixaban")], params)
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.MAJOR
        assert findings[0].threshold_ml_min == 30.0
        assert findings[0].crcl_ml_min < 30
        assert findings[0].egfr_ml_min < 30
        assert "apixaban" in findings[0].explanation

    def test_moderate_finding_when_the_two_equations_diverge_at_the_threshold(self) -> None:
        # 80yo female, 45kg, Scr=1.3, 155cm: CrCl ~24.5 (below 30), eGFR
        # ~33.7 (above 30) — the two equations land on opposite sides of
        # apixaban's threshold, the genuine "standard in flux" divergence
        # ADR-0005 exists to surface.
        params = RenalParameters(
            age_years=80, weight_kg=45, sex="female", serum_creatinine_mg_dl=1.3, height_cm=155
        )
        findings = check_renal_thresholds([_medication("apixaban")], params)
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.MODERATE
        assert findings[0].crcl_ml_min < 30
        assert findings[0].egfr_ml_min >= 30
        assert "disagree" in findings[0].explanation

    def test_aminoglycoside_uses_the_60_ml_min_threshold(self) -> None:
        # CrCl/eGFR both land between apixaban's 30 threshold and
        # vancomycin's 60 threshold -> flagged for vancomycin, not (if it
        # were present) a DOAC.
        params = RenalParameters(
            age_years=70, weight_kg=65, sex="male", serum_creatinine_mg_dl=1.4, height_cm=172
        )
        findings = check_renal_thresholds([_medication("vancomycin")], params)
        assert len(findings) == 1
        assert findings[0].threshold_ml_min == 60.0

    def test_drug_name_matching_is_case_insensitive(self) -> None:
        params = RenalParameters(
            age_years=85, weight_kg=50, sex="male", serum_creatinine_mg_dl=3.0, height_cm=170
        )
        findings = check_renal_thresholds([_medication("Apixaban")], params)
        assert len(findings) == 1

    def test_threshold_matches_via_ingredient_match_names_not_the_branded_display_name(
        self,
    ) -> None:
        """Regression (N1): the real normalization pipeline sets ``name`` to
        RxNav's canonical name — often a verbose branded product string that
        can never equal an ingredient threshold key. Matching must go
        through ``match_names`` (ingredients + parsed name), or the renal
        check silently never fires for real normalized input."""
        params = RenalParameters(
            age_years=85, weight_kg=50, sex="male", serum_creatinine_mg_dl=3.0, height_cm=170
        )
        branded = NormalizedMedication(
            raw_text="Eliquis 5mg BID",
            name="apixaban 5 MG Oral Tablet [Eliquis]",
            rxcui="562282",
            dose="5mg",
            route=None,
            frequency=None,
            match_names=("apixaban", "eliquis"),
        )
        findings = check_renal_thresholds([branded], params)
        assert len(findings) == 1
        assert findings[0].threshold_ml_min == 30.0
        assert findings[0].rule_id == "renal_threshold:apixaban"

    def test_only_threshold_sensitive_medications_in_a_mixed_list_get_findings(self) -> None:
        params = RenalParameters(
            age_years=85, weight_kg=50, sex="male", serum_creatinine_mg_dl=3.0, height_cm=170
        )
        findings = check_renal_thresholds(
            [_medication("metformin"), _medication("apixaban"), _medication("lisinopril")],
            params,
        )
        assert len(findings) == 1
        assert findings[0].medication_index == 1
