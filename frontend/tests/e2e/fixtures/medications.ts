/**
 * Reusable medication-list test input (avoids recreating ad-hoc strings
 * per-spec). Warfarin + aspirin is a real, well-established interacting
 * pair — the same one used in the backend's golden-snapshot fixture
 * (backend/tests/database/test_medication_interactions.py) — so this text
 * exercises a genuine finding whenever a real LLM provider is configured,
 * not just the degraded-mode path.
 */
export const INTERACTING_MEDICATION_LIST = 'warfarin 5mg daily\naspirin 81mg daily';

/** A single threshold-sensitive medication (apixaban, ADR-0005's DOAC
 * example) paired with severely-impaired-renal-function parameters — the
 * same case pinned as a backend golden test
 * (backend/tests/unit/test_medication_renal.py::
 * test_major_finding_when_both_equations_agree_renal_function_is_impaired),
 * so both equations land below apixaban's 30 mL/min threshold whenever a
 * real LLM provider is configured. */
export const RENAL_THRESHOLD_MEDICATION_LIST = 'apixaban 5mg twice daily';

export const IMPAIRED_RENAL_PARAMETERS = {
  ageYears: '85',
  weightKg: '50',
  sex: 'male' as const,
  serumCreatinineMgDl: '3.0',
  heightCm: '170',
};

/** A single medication for PIP screening (Beers 2023 + STOPP/START v3,
 * ADR-0019) — the age/condition pair alone is enough to trigger the check,
 * independent of renal parameters. */
export const PIP_SCREENING_MEDICATION_LIST = 'diphenhydramine 25mg nightly';

export const PIP_SCREENING_PARAMETERS = {
  ageYears: '78',
  conditions: 'insomnia',
};

/** Two medication lists for discrepancy classification (ADR-0019) — a
 * dose change plus an added medication between "previous" and "current". */
export const PREVIOUS_MEDICATION_LIST = 'metformin 500mg once daily';
export const CURRENT_MEDICATION_LIST_WITH_DISCREPANCY =
  'metformin 1000mg once daily\nlisinopril 10mg once daily';
