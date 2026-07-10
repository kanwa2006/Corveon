/**
 * Reusable medication-list test input (avoids recreating ad-hoc strings
 * per-spec). Warfarin + aspirin is a real, well-established interacting
 * pair — the same one used in the backend's golden-snapshot fixture
 * (backend/tests/database/test_medication_interactions.py) — so this text
 * exercises a genuine finding whenever a real LLM provider is configured,
 * not just the degraded-mode path.
 */
export const INTERACTING_MEDICATION_LIST = 'warfarin 5mg daily\naspirin 81mg daily';
