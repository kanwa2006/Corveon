# Corveon — Phased Build Roadmap

Respects the strict per-feature order (Architecture → Database → API → Backend → Frontend →
Testing → Docs). Each phase ends with all relevant test layers green in CI. Buildable on free infra.

## Phase 0 — Foundation ✅ (this repository)
Repository structure, standards, documentation set, CLAUDE.md, ADR log, CI/CD skeleton, env
contract. No application code. Self-review complete.

## Week 1 — MVP core
- ✅ Auth + users (OAuth2/JWT, Argon2, RBAC) — backend (register/login/refresh/logout/me) +
  frontend (login/register, httpOnly-cookie session via BFF proxy, ADR-0012).
- ✅ Chat CRUD with **per-chat isolation** (app guard + Postgres RLS, verified with a genuine
  cross-user bypass-attempt test + repo invariant, ADR-0013) — backend (create/list/get/rename/
  pin/archive/delete) + frontend (chat list with search/filter, chat detail, dashboard preview).
- ✅ Single-provider chat (Gemini + Ollama, ADR-0006 registry) with **SSE streaming** direct from
  the backend (ADR-0007), bridged from the httpOnly-cookie session via a short-lived stream ticket
  (ADR-0016) — backend (fast-path/RAG-grounded orchestrator slice) + frontend (message thread,
  streaming composer).
- ✅ PDF upload → parse → chunk → embed → **in-chat** semantic search — backend (ARQ ingestion
  pipeline: validate/extract/chunk/embed/index; pgvector HNSW search filtered by `chat_id` +
  `model_id`, ADR-0008/0015) + frontend (upload with live per-stage progress, document list).
- ✅ Minimal dashboard (auth landing page + recent-chats preview; message UI now live on the chat
  detail page).
- ✅ Core tests + CI green — backend (ruff/format/mypy --strict/pytest 155 passed/Alembic sync
  check/bandit/pip-audit), frontend (lint/typecheck/38 unit tests/build), and a full-stack
  Playwright **e2e + a11y** job (14/14) wired into CI against a live Postgres+Redis+backend+worker.

## Month 1 — Provider layer & orchestration
- ✅ Provider-agnostic layer: key pools, failover, **health monitoring + circuit breaker**
  (`app/providers/health.py`), per-provider **token-bucket** rate limiting + per-request **LLM call
  budget** (`app/providers/budget.py`), provider call metrics/structured logging
  (`app/providers/metrics.py`), **degraded/absent-provider handling preserved** (§23.1/§23.2). All
  five catalog providers now adapt: Gemini, Ollama, **Anthropic** (Messages API), and **OpenAI** /
  **OpenRouter** (shared OpenAI-compatible base, `app/providers/openai_compatible.py` —  one adapter
  per wire protocol, not per vendor) — each registered only when its key pool is configured.
- ✅ Orchestrator + deterministic routing policy + `routing_trace`; **fast-path** (§23.5); per-request
  LLM budget enforced. A 4-way routing policy (`fast_path` / `pure_llm` / `rag_grounded` /
  `rag_no_match`) built from Query Understanding, Task Planning, and Retrieval steps implemented as
  `Agent` protocol classes (`app/agents/{query_understanding,task_planning,retrieval}.py`, blueprint
  §7) over a shared `OrchestratorState` (`app/agents/state.py`) — honestly scoped to the two
  subsystems that exist today (chat + documents); the other five blueprint branches (public evidence,
  org-trusted, multi-agent verification, external lookup) land as new agent files once Month 3/6-12
  build the subsystems they need, not a rewrite.
- ✅ Multi-format ingestion (DOCX/PPT/MD/images + OCR). A MIME-keyed parser registry
  (`app/ingestion/parsing.py::parse_document`) dispatches to `parse_pdf` / `parse_docx` /
  `parse_pptx` / `parse_markdown` / `parse_image`; scanned (image-only) PDF pages fall back to
  Tesseract OCR automatically. The upload endpoint derives the canonical MIME type from the file
  extension (not the client's `Content-Type`, which is inconsistent across browsers for less-common
  types) and validates with per-format magic bytes or UTF-8 decodability.
- ✅ Export (MD/PDF). `POST /chats/{id}/messages/{mid}/export {format: md|pdf}` — synchronous
  (`app/export/message_export.py`), preserving citations (from `routing_trace.retrieved_chunks`)
  and metadata (role, timestamp, routing path/provider/status). PDF uses fpdf2's core Latin-1 font
  with a documented transliteration fallback for out-of-range characters (no bundled Unicode font).
- ✅ Observability: append-only **audit log** (`app/data/models/audit_log.py`, migration `0004`) —
  actor/action/entity/IP/metadata, wired into every sensitive action named in CLAUDE.md §8
  (register/login/logout, document upload/delete, message export) via `AuditLogRepository`, verified
  by querying the table directly (`tests/database/test_audit_log.py`, no admin-read endpoint yet).
  Per-provider-attempt and per-request OTel spans (`provider.stream_chat`, `orchestrator.plan_task`,
  `orchestrator.generate_response`) added alongside the existing Prometheus counters/histograms and
  structlog `trace_id` propagation from Week 1. Grafana dashboards and Sentry wiring stay out of
  scope until there's a deployed environment to point them at — building unusable config against
  nothing would violate the "no half-finished implementations" rule, not satisfy it.
- ✅ Expanded test matrix: the two test layers `docs/DEVELOPER.md` had declared (dependencies
  installed, never wired) are now real. **API contract** (`schemathesis`, CI job `contract`):
  property-based fuzzing against the live OpenAPI schema, scoped to the `not_a_server_error` check —
  it caught a genuine bug (see CHANGELOG: `validation_error_handler` itself crashing into a 500 on
  certain malformed input). Broader checks (`status_code_conformance` etc.) were evaluated and
  rejected for CI: they flag every route returning a correct-but-undocumented 401/404/422, which is
  an OpenAPI-metadata completeness gap across ~20 endpoints, not a contract violation — fixing that
  honestly is its own bounded follow-up, not something to bundle in here. **Performance** (`locust`,
  same CI job): a concurrency smoke — asserts zero request failures under 5 concurrent simulated
  users, not a latency gate (shared CI runners don't give reproducible latency numbers; run
  `locust -f tests/performance/locustfile.py --host <url>` locally for real numbers). The
  `tests/integration` layer in `docs/DEVELOPER.md`'s table is intentionally not a separate suite —
  `tests/api`, `tests/database`, and `tests/security` already run against real Postgres+Redis
  (GitHub Actions services), which is what that layer is actually for; adding a parallel
  Testcontainers-spun Postgres would duplicate infrastructure, not coverage.
- ✅ Blueprint reconciliation pass (docs/specifications/corveon-master-implementation-blueprint-v1.0.md
  saved as the permanent reference; see that reconciliation for the full list). Closed every
  concrete Month 1-scope gap found: chat deletion now cleans up its documents' object-storage blobs
  via a fire-and-forget ARQ job and writes one `audit_log` entry for the action (§23.6); the
  embedding-model-change reindex job exists (`app/workers/tasks.py::reindex_chat_chunks`, §23.4,
  triggered per-chat — a system-wide admin trigger endpoint is deferred until admin RBAC/endpoints
  exist, since none do yet); `infra/docker-compose.yml` now runs `api`/`worker` against the same
  production image (`infra/docker/backend.Dockerfile`), which surfaced and fixed two real bugs: a
  missing `.venv312`-style pattern in `.dockerignore` was uploading a 1.5GB build context, and seven
  `.env.example` variables with an empty default plus a trailing comment (`KEY=    # comment`) were
  parsed correctly by python-dotenv but not by Docker Compose's `env_file`, silently poisoning
  `OLLAMA_RPM_LIMIT` (typed `int | None`) enough to crash container startup; OCR is now its own
  ingestion progress stage for image uploads, where it's knowable upfront (§12). Month 3 (Evidence
  Verification Engine) intentionally not started per explicit scope decision.

## Month 3 — Evidence Verification Engine
- ✅ Six public connectors (`app/evidence/connectors/`) — PubMed, DailyMed, openFDA,
  ClinicalTrials.gov, MeSH, RxNorm — each a plain-httpx client (no SDK) behind a common
  `EvidenceConnector` protocol, cache-first (Redis, [ADR-0017](adr/0017-evidence-cache-via-redis-not-postgres-table.md))
  and non-blocking rate-limited (`TokenBucket`, reused unmodified from Month 1). A connector never
  raises for not-found/rate-limited — returns `[]`, treated as reduced coverage, not a hard error.
- ✅ Evidence retrieval layer (`app/evidence/retrieval.py`, `app/evidence/registry.py`) fans out to
  every connector concurrently and merges with this chat's own uploaded-document chunks (reusing
  Month 1's `ChunkRepository`/`EmbeddingModel` RAG primitives at the same relevance threshold).
- ✅ Provenance model + source classification (`app/evidence/scoring.py::classify_source`) — five
  source classes (uploaded document, verified public, org-trusted, AI reasoning,
  conflicting/insufficient); a three-way per-excerpt stance (supports/contradicts/irrelevant, not a
  boolean) is what makes genuine conflict detection possible.
- ✅ Deterministic confidence scoring (`score_confidence`, no LLM) — a documented additive composite
  of source-class weight, independent-source agreement, recency, and citation-resolution rate,
  always reconstructable from its own rationale string.
- ✅ Conflict detection + misinformation/outdated/unsupported flagging (`app/evidence/analysis.py`) —
  one LLM call per claim (not per citation, keeps the per-request LLM-call budget bounded) comparing
  the claim against every retrieved excerpt at once; flags are only ever raised from concrete
  evidence, never guessed.
- ✅ Citation verification / fabricated-citation guard (`app/evidence/citation_verification.py`) —
  structurally prevented by construction (citations only ever come from a connector's parsed API
  response, never LLM-generated text), plus a narrower structural-completeness check so an
  incomplete connector result is flagged, not shown.
- ✅ Evidence Verification API — `POST /chats/{id}/verify` (`app/api/routers/evidence.py`), SSE,
  streaming one scored claim at a time as it completes rather than batching (see
  [API.md](API.md#evidence--medication)); reuses the exact stream-ticket bridge (ADR-0016) and
  `LLMCallBudget`/provider-registry seams Month 1 built, no new abstractions.
- ✅ Frontend Evidence Verification UI — a "Verify claims" trigger on assistant messages
  (`components/chats/evidence-verification-panel.tsx`) streaming claims in with a source-class
  badge (the five `evidence-*` design tokens already reserved in Week 1), a confidence meter,
  detection flags, and linked citations.
- ✅ Tests written alongside each feature — backend unit (connectors against `httpx.MockTransport` +
  real Redis, claim extraction/analysis/scoring/citation-verification, the full verification-service
  pipeline mocking only the DB-touching repositories per this codebase's existing convention), API
  (the full `/verify` SSE round trip, happy path + degraded mode), database (RLS isolation for all
  three new tables); frontend unit/hook/component tests plus a live browser check against the real
  running backend.
- ⏭ Org-trusted sources (versioned, access-scoped connectors) — explicitly out of this phase's scope
  by an explicit scope decision; `SourceClass.ORG_TRUSTED` is a real, reserved enum value that no
  connector produces yet, not a placeholder.
- ⏭ Premium dashboards/analytics — not started; no `analytics`/`audit` read endpoints exist yet
  (audit *writing* for the verify action itself is done, via `AuditLogRepository`, matching every
  other sensitive action named in CLAUDE.md §8).

## Month 6–12 — Medication-Safety Engine (full) & enterprise

### Phase 1 — Normalization + drug-drug interaction detection ✅
- ✅ Data model: `medications` / `medication_findings` / `drug_data_snapshots` / `drug_interactions`
  (migration `0006`), chat-scoped tables RLS-isolated exactly like every other content table;
  `drug_data_snapshots`/`drug_interactions` are deliberately excluded from RLS — shared reference
  data, not per-chat content.
- ✅ DDInter 2.0 pinned, checksummed snapshot loader (`app/medication/ddinter_loader.py`,
  [ADR-0018](adr/0018-ddinter-loader-location-and-no-bundled-dataset.md)) — never fetched at request
  time; the real 302k-row dataset isn't bundled (not fetchable/licensed-to-vendor in this
  environment), so it ships as real, production-ready, checksum-verified infrastructure an operator
  points at a provisioned export, not fabricated data.
- ✅ RxNorm normalization + **DDInter 2.0** (pinned) with **openFDA label fallback** (ADR-0004) —
  `app/medication/normalizer.py` (LLM-guardrailed free-text → structured entries, one LLM call per
  request) + `app/medication/rxnorm_client.py` (RxCUI lookup) + `app/medication/interactions.py`
  (deterministic pairwise DDI rules engine, no LLM) + `app/medication/openfda_ddi_client.py`
  (label-text fallback, tagged `unclassified` severity — the FDA's own words, not a synthesized
  severity tier).
- ✅ API — `POST /chats/{id}/medications/analyze` (SSE, `medication`/`interaction`/`done`/`error`
  events, same stream-ticket bridge as `/verify`) returning `{normalized[], interactions[]}` only;
  `renal[]`/`pip_flags[]`/`discrepancies[]` are later phases below, not stubbed.
- ✅ Frontend — a medication-list input + streamed results panel
  (`components/chats/medication-panel.tsx`) on the chat detail page, mirroring the Evidence
  Verification UI's established pattern.
- ✅ Tests written alongside each feature — golden tests against a pinned snapshot (real,
  well-established textbook interactions, not fabricated), RLS isolation, API (happy path +
  degraded mode), unit tests for the loader/normalizer/rules engine/openFDA fallback, frontend
  unit/hook/component tests plus a live browser verification (real Gemini parse + real RxNav
  lookups) against the real running backend.

### Later phases — not yet implemented
- **Dual renal equations** — Cockcroft-Gault + 2021 race-free CKD-EPI, divergence flags (ADR-0005).
- **Beers 2023** + **STOPP/START v3** screens; medication-discrepancy classification.
- Guardrailed LLM explanations (no ungrounded facts).
- Multi-agent depth; enterprise path (Qdrant option, SSO, read replicas, on-prem/Ollama).
- Accessibility + performance audits; reproducible snapshot automation.

## Cross-cutting, always-on
Per-feature Definition of Done · docs updated per PR · ADR per resolved decision · golden tests for
rules · no cross-chat reads · no hardcoded providers · no confident answers on suspected misinformation.
