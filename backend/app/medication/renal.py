"""Deterministic renal-function calculation and threshold checks (blueprint
§9, ADR-0005) — dual equations, no LLM anywhere in this module (CLAUDE.md
§6: "the rules engine is the source of truth").

Implements **both** kidney-function equations rather than picking one,
because the clinical standard is actively in transition (ADR-0005):
- Cockcroft-Gault creatinine clearance (CrCl, mL/min) — the historical
  FDA/drug-label standard, still embedded in most FDA-approved labels.
- 2021 race-free CKD-EPI creatinine eGFR (mL/min/1.73m²) — recommended by
  the NKF-ASN Task Force (Inker et al., NEJM 2021;385:1737-1749) and 2024
  FDA guidance for PK/dosing; de-indexed to the patient's actual body
  surface area (DuBois formula) when used for dosing, per ADR-0005.

Threshold table: a deliberately small, conservative first pass covering
only the blueprint's own named examples (DOACs, aminoglycosides,
vancomycin) — matched by generic drug name, case-insensitively. Each
threshold is a single, commonly-cited renal-dose-adjustment decision point
for that drug class, not a full per-label dosing table; a finding always
carries both raw computed values so a clinician can verify against the
actual label rather than trusting a single derived number (CLAUDE.md:
never state a fact with more confidence than the underlying data
supports).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.data.models.medication import FindingSeverity
from app.medication.interactions import NormalizedMedication

Sex = Literal["male", "female"]


@dataclass(frozen=True, slots=True)
class RenalParameters:
    age_years: int
    weight_kg: float
    sex: Sex
    serum_creatinine_mg_dl: float
    height_cm: float


@dataclass(frozen=True, slots=True)
class RenalFinding:
    medication_index: int
    crcl_ml_min: float
    egfr_ml_min: float
    threshold_ml_min: float
    severity: FindingSeverity
    rule_id: str
    explanation: str


# (drug class, generic names, renal-dose-adjustment decision threshold in
# mL/min). DOAC threshold: the commonly-cited severe-renal-impairment
# dosing decision point across apixaban/dabigatran/rivaroxaban/edoxaban
# labels. Aminoglycoside/vancomycin threshold: the standard renal-dosing
# trigger point for these nephrotoxic, renally-cleared antibiotics.
_THRESHOLD_SENSITIVE_DRUGS: dict[str, float] = {
    "apixaban": 30.0,
    "dabigatran": 30.0,
    "rivaroxaban": 30.0,
    "edoxaban": 30.0,
    "vancomycin": 60.0,
    "gentamicin": 60.0,
    "tobramycin": 60.0,
    "amikacin": 60.0,
}


def cockcroft_gault_crcl(params: RenalParameters) -> float:
    """CrCl (mL/min) = [(140 - age) x weight(kg) x (0.85 if female)] /
    (72 x serum creatinine mg/dL)."""
    base = (140 - params.age_years) * params.weight_kg
    if params.sex == "female":
        base *= 0.85
    return base / (72 * params.serum_creatinine_mg_dl)


def _body_surface_area_m2(params: RenalParameters) -> float:
    """DuBois formula: BSA (m^2) = 0.007184 x height(cm)^0.725 x weight(kg)^0.425."""
    # float ** float is typed Any in typeshed (a negative base could yield a
    # complex result) — explicit float() asserts the real-valued case this
    # domain always has (height/weight are always positive).
    return float(0.007184 * params.height_cm**0.725 * params.weight_kg**0.425)


def ckd_epi_2021_egfr(params: RenalParameters) -> float:
    """2021 race-free CKD-EPI creatinine eGFR, de-indexed from
    mL/min/1.73m^2 to the patient's actual mL/min via their own BSA
    (ADR-0005) — the form relevant to drug dosing, not the screening form."""
    kappa = 0.7 if params.sex == "female" else 0.9
    alpha = -0.241 if params.sex == "female" else -0.302
    scr_over_kappa = params.serum_creatinine_mg_dl / kappa
    indexed = (
        142
        * min(scr_over_kappa, 1.0) ** alpha
        * max(scr_over_kappa, 1.0) ** -1.200
        * 0.9938**params.age_years
    )
    if params.sex == "female":
        indexed *= 1.012
    bsa = _body_surface_area_m2(params)
    return float(indexed * (bsa / 1.73))


def check_renal_thresholds(
    medications: list[NormalizedMedication], params: RenalParameters
) -> list[RenalFinding]:
    """Runs both equations once, then checks every threshold-sensitive
    medication against its decision point. A finding's severity reflects
    what the two equations agree or disagree on:
    - MAJOR: both equations place the patient below the drug's threshold —
      clear renal impairment relevant to this drug's dosing.
    - MODERATE: the two equations land on different sides of the
      threshold — the genuine "standard in flux" divergence ADR-0005
      exists to surface, not silently resolved toward one equation.
    No finding is produced when both equations agree the patient is above
    threshold — nothing renal-relevant to flag for that drug."""
    crcl = cockcroft_gault_crcl(params)
    egfr = ckd_epi_2021_egfr(params)

    findings: list[RenalFinding] = []
    for index, medication in enumerate(medications):
        # Threshold keys are generic ingredient names — match against the
        # medication's ingredient/parsed match names, never the display
        # name (RxNav canonical names are often verbose branded strings).
        matched_name: str | None = None
        threshold: float | None = None
        for candidate in medication.names_for_matching:
            threshold = _THRESHOLD_SENSITIVE_DRUGS.get(candidate)
            if threshold is not None:
                matched_name = candidate
                break
        if threshold is None or matched_name is None:
            continue

        crcl_below = crcl < threshold
        egfr_below = egfr < threshold
        if not crcl_below and not egfr_below:
            continue

        if crcl_below == egfr_below:
            severity = FindingSeverity.MAJOR
            explanation = (
                f"Both Cockcroft-Gault CrCl ({crcl:.1f} mL/min) and CKD-EPI 2021 eGFR "
                f"({egfr:.1f} mL/min) are below {medication.name}'s "
                f"{threshold:.0f} mL/min renal-dosing decision threshold — verify "
                f"against the current label before dosing."
            )
        else:
            severity = FindingSeverity.MODERATE
            explanation = (
                f"Cockcroft-Gault CrCl ({crcl:.1f} mL/min) and CKD-EPI 2021 eGFR "
                f"({egfr:.1f} mL/min) disagree on whether renal function is below "
                f"{medication.name}'s {threshold:.0f} mL/min renal-dosing decision "
                f"threshold — the two equations diverge at this patient's values; "
                f"clinical judgment is needed on which to weight."
            )

        findings.append(
            RenalFinding(
                medication_index=index,
                crcl_ml_min=round(crcl, 1),
                egfr_ml_min=round(egfr, 1),
                threshold_ml_min=threshold,
                severity=severity,
                rule_id=f"renal_threshold:{matched_name}",
                explanation=explanation,
            )
        )
    return findings
