# ADR-0024: Ollama-only deployment mode

- **Status:** Accepted
- **Date:** 2026-07-11

## Context
"Enterprise path" (blueprint, `docs/ROADMAP.md`) lists on-prem/Ollama hardening as future work
(SSO and read replicas — ADR-0023 — are separate, already-covered milestones). A regulated or
data-residency-sensitive deployment (e.g. a hospital, per `docs/DEPLOYMENT.md`) wants a
**code-enforced guarantee**, not just an operator's promise, that the AI chat and evidence-retrieval
paths never call out to a cloud AI provider or a public medical-evidence API — only local Ollama.

Two subsystems are already unconditionally "always on," with no absence state, unlike the AI
providers (ADR-0006): the six evidence connectors (`app/evidence/registry.py`, PubMed/DailyMed/
openFDA/ClinicalTrials.gov/MeSH/RxNorm) and the Medication-Safety Engine's `RxNormClient`/
`OpenFdaDdiClient` (RxNav normalization, openFDA DDI fallback). All of these make live outbound
HTTP calls today regardless of which AI provider is in use.

## Decision
One setting, `DEPLOYMENT_MODE: Literal["standard", "ollama_only"] = "standard"`. When
`ollama_only`:
- `build_provider_registry` (`app/providers/registry.py`) skips registering Gemini/Anthropic/
  OpenAI/OpenRouter **even if their API keys are set** — only Ollama is ever registered. This is
  a stronger guarantee than simply leaving keys blank: an operator's leftover key in `.env` cannot
  accidentally re-enable a cloud provider.
- `app.state.evidence_connectors` is built as an empty `EvidenceConnectorRegistry({})` instead of
  `build_evidence_connector_registry(...)` — zero connectors registered. This single choke point
  is enough to disable both consumers: the Evidence Verification endpoint (`search_all` over zero
  connectors returns `{}` immediately, no crash — the registry's own existing contract) and the
  chat orchestrator's `PublicEvidenceAgent` (an empty result set falls through the *already-built*
  "no public evidence found → `PURE_LLM`" path in `TaskPlanningAgent`, ADR-0021 — no orchestrator
  change needed).
- `RxNormClient`/`OpenFdaDdiClient` each gain a constructor-level `enabled: bool = True` flag;
  their public methods (`normalize`/`check_pair`) short-circuit to `None` when disabled, before
  touching the token bucket, cache, or network — reusing their own existing "`None` is a normal,
  non-error result" contract, so no caller (`app/medication/analysis_service.py`,
  `interactions.py`, `normalizer.py`) needs to change.

## Consequences
- Zero behavior change when `DEPLOYMENT_MODE` is left at its default (`standard`) — every existing
  deployment, test, and endpoint is unaffected.
- No new subsystem, no schema change, no Alembic migration — the flag composes entirely at the
  process-startup composition root (`app/main.py`'s `lifespan`) plus two small, contract-preserving
  guard clauses in the two medication clients.
- What this flag does **not** cover, by design, left as documented future work: the Medication-
  Safety Engine's pinned-snapshot sync (`app/medication/snapshot_sync.py`) already reads only local
  files, and `LocalDiskStorage` (ADR-0014) already has no network dependency — neither needed a
  change. `OTEL_EXPORTER_OTLP_ENDPOINT` and R2 object storage remain separately opt-in and unset by
  default already; an operator who explicitly configures either of those in an otherwise
  `ollama_only` deployment is making an explicit choice this flag does not override.
- Naming is deliberately `ollama_only`, not "air-gapped" — this flag guarantees the *AI chat and
  evidence-retrieval* paths make zero external calls; it does not certify the entire deployment
  (network egress policy, OS-level isolation, etc.) as air-gapped. Overclaiming the latter would be
  a safety-relevant misrepresentation this codebase's own "never state a fact with more confidence
  than the source supports" posture (CLAUDE.md) argues against applying to itself.

## Alternatives considered
- **A bare `AIR_GAPPED_MODE: bool`:** rejected for the naming reason above — "air-gapped" implies a
  stronger, whole-deployment guarantee than this change actually provides.
- **Making `rxnorm_client`/`openfda_ddi_client`/`evidence_connectors` `None` in air-gapped mode
  instead of contract-preserving no-op/empty instances:** rejected — would require updating every
  consumer (`app/api/deps.py`'s dependency functions, `analysis_service.py`) to handle `None`,
  touching files outside this milestone's scope for no behavioral benefit over the chosen approach.
- **A single blanket `settings.is_ollama_only` check duplicated in every consumer file:** rejected —
  the composition-root approach (gate what gets *built* once, in `main.py`) is smaller, and every
  consumer already has a "no result from this source" path to fall through to, so it needs no
  awareness of deployment mode at all.
