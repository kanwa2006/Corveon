# ADR-0005: Dual renal-function equations (Cockcroft-Gault + 2021 CKD-EPI)

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
Renal dose adjustment is safety-critical, and the clinical standard is actively in transition.
Cockcroft-Gault CrCl is embedded in most FDA-approved labels; the 2021 race-free CKD-EPI eGFR is
recommended by the NKF-ASN Task Force and by 2024 FDA guidance for PK/dosing.

## Decision
Implement **both**:
- **Cockcroft-Gault CrCl (mL/min)** — the historical FDA/label standard.
- **2021 race-free CKD-EPI creatinine eGFR** — de-indexed to the patient's actual body surface area
  (mL/min/1.73m² → mL/min) when used for drug dosing.
Show both, and **flag divergence at critical decision thresholds** (e.g., apixaban and other DOACs,
aminoglycosides, vancomycin).

## Consequences
- Hedges a standard in flux; clinicians see both numbers and any disagreement at decision points.
- Deterministic and testable via golden tests.
- Tradeoff: more inputs required (age, weight, sex, serum creatinine, height/BSA); handled by the
  ingestion normalizer with clear "insufficient data" states.

## Alternatives considered
- **Single equation:** simpler but silently picks a side of an unsettled standard — unacceptable for
  a safety feature.
