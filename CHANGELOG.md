# Changelog

All notable changes to Corveon are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Roadmap phases that map to future releases are tracked in [docs/ROADMAP.md](docs/ROADMAP.md).

## [Unreleased]

### Added
- **Medication-Safety Engine, Phase 1: normalization + drug-drug interaction detection** (Roadmap
  Month 6-12, first slice): given free text describing a patient's medications, parses it into
  structured entries, normalizes each to RxCUI via RxNorm, persists them, then runs a deterministic
  DDI rules engine and persists its findings — `POST /chats/{id}/medications/analyze` (SSE, streams
  one result at a time as it completes). Strictly scoped to normalization + DDI detection; renal
  checks (Phase 2, below), Beers/STOPP-START screens, discrepancy classification, and guardrailed
  explanations are explicitly later phases of this same engine — see
  [docs/ROADMAP.md](docs/ROADMAP.md) Month 6-12 for the full done/deferred breakdown.
  - Data model: `medications` / `medication_findings` / `drug_data_snapshots` / `drug_interactions`
    (migration `0006`); the chat-scoped pair gets the same triple-enforced isolation as every other
    content table, while the snapshot/interaction pair is deliberately unscoped, shared reference
    data.
  - DDInter 2.0 pinned, checksummed snapshot loader
    (`backend/app/medication/ddinter_loader.py`, [ADR-0018](docs/adr/0018-ddinter-loader-location-and-no-bundled-dataset.md))
    — never fetched at request time. The real 302k-row DDInter dataset isn't fetchable or licensed
    to vendor in this environment, so the loader ships as real, checksum-verified infrastructure an
    operator points at a provisioned export; dev/test uses a small, explicitly-labeled fixture of
    real, well-established textbook interactions (warfarin+aspirin, etc.) — never fabricated data,
    per CLAUDE.md's golden rule.
  - RxNorm normalization (`app/medication/rxnorm_client.py`) and free-text parsing
    (`app/medication/normalizer.py`) — deliberately separate, minimal modules from the Evidence
    Verification Engine's own RxNorm/openFDA connectors (different domain, different return shape),
    not a reuse that would couple the two engines' evolution together. Parsing is the only LLM call
    in the whole pipeline (one per request, through the existing provider registry/budget), strictly
    guardrailed to extract only name/dose/route/frequency already present in the text.
  - Deterministic DDI rules engine (`app/medication/interactions.py`) — DDInter 2.0 primary,
    openFDA label-text fallback (`app/medication/openfda_ddi_client.py`) for pairs the snapshot
    doesn't cover, surfaced as the FDA's own label language (`FindingSeverity.UNCLASSIFIED`) rather
    than a synthesized severity the source didn't provide. No LLM involvement anywhere in this
    module — the rules engine is the source of truth (CLAUDE.md §6).
  - `POST /chats/{id}/medications/analyze` (`app/api/routers/medication.py`) — 202 + SSE, same
    shape and stream-ticket bridge (ADR-0016) as `POST /chats/{id}/verify`: a `medication` event
    per normalized/persisted medication, an `interaction` event per DDI finding, a final `done`
    event, or an `error` event on a degraded-mode condition. Audit-logged (`medication.analyze`).
  - Frontend: a medication-list input + streamed results panel
    (`components/chats/medication-panel.tsx`) on the chat detail page — source-class-style severity
    badges (evidence-* design tokens), RxCUI match indicators, and linked openFDA label sources —
    mirroring the Evidence Verification UI's established pattern.
  - Tests written alongside each feature: golden tests against the pinned snapshot (real textbook
    interactions), database RLS isolation, API (happy path, degraded mode), unit tests for the
    loader/normalizer/rules engine/openFDA client, frontend unit/hook/component tests, plus a live
    browser verification (real Gemini parse + real RxNav lookups) against the running backend.
- **Medication-Safety Engine, Phase 2: renal/dose checks** (Roadmap Month 6-12, ADR-0005): extends
  the existing `POST /chats/{id}/medications/analyze` endpoint (no new endpoint) with optional
  renal parameters and a `renal` SSE event — deterministic Cockcroft-Gault CrCl + 2021 race-free
  CKD-EPI eGFR (de-indexed to the patient's own body surface area), checked against a small,
  documented table of threshold-sensitive drug classes (DOACs, aminoglycosides, vancomycin).
  - `app/medication/renal.py` — both equations implemented rather than one, since the clinical
    standard is actively in transition (ADR-0005); reference values cross-checked against the
    NKF/ASN CKD-EPI 2021 calculator and standard Cockcroft-Gault worked examples before being
    pinned as golden tests. No LLM involvement — purely deterministic, like the DDI rules engine.
  - A finding's severity distinguishes clear renal impairment (both equations agree the patient is
    below a drug's threshold, `major`) from genuine equation **divergence** (the two equations land
    on opposite sides of the threshold, `moderate`) — the exact "hedge a standard in flux" case
    ADR-0005 exists to surface, never silently resolved toward one equation.
  - Renal parameters (age/weight/sex/serum creatinine/height) are optional and all-or-nothing on
    the request — a `model_validator` rejects a partial set with a `422` rather than silently
    skipping renal checks, so an incomplete submission never fails quietly with no explanation.
    Omitting all five is the normal opt-out case (an honest "insufficient data" state, ADR-0005).
  - `InteractionSource` gains a `calculated` member (migration `0007`, `ALTER TYPE ... ADD VALUE`)
    for formula-derived findings, alongside the existing `ddinter`/`openfda_label` external-lookup
    sources — the enum's Phase-1 name is kept (not renamed) to avoid touching unrelated Phase 1
    code; its docstring now explains the reuse.
  - Frontend: an optional, collapsible renal-parameter input section and renal-finding cards
    (CrCl/eGFR/threshold values, severity badge) in the existing medication panel — no new page.
  - Tests written alongside the feature: golden tests for both equations plus the threshold/
    divergence rules (11 cases), API tests (renal finding present when parameters are supplied,
    absent when omitted, `422` on a partial set), frontend unit/component tests, and new Playwright
    e2e coverage using reusable fixtures (`tests/e2e/fixtures/medications.ts`) rather than inline
    ad-hoc test strings.
- **Medication-Safety Engine, Phase 3: PIP screening + discrepancy classification + guardrailed
  narrative** (Roadmap Month 6-12, ADR-0019/ADR-0020): extends the existing
  `POST /chats/{id}/medications/analyze` endpoint (no new endpoint) with potentially-inappropriate-
  prescribing screening (AGS Beers Criteria 2023 + STOPP/START v3), a diff between the request's
  current and an optional previous medication list, and an optional guardrail-checked LLM narrative
  layered on those two new finding types.
  - Data model: `pip_criteria` (migration `0008`) — shared reference data (like `drug_interactions`),
    FK'd to the existing `drug_data_snapshots`; `medication_findings.medication_a_id` made nullable,
    since a START-criterion finding flags a medication *absent* from the current list and has no
    medication row to anchor to (ADR-0019).
  - Beers 2023 + STOPP/START v3 pinned, checksummed snapshot loader
    (`app/medication/pip_loader.py`) — same pattern as DDInter (ADR-0018): never fetched at request
    time, the real copyrighted criteria tables aren't bundled; dev/test uses a small, explicitly
    synthetic fixture structurally representative of the real row shape.
  - PIP screening engine (`app/medication/pip_screening.py`, deterministic, no LLM) — age ≥65 gate;
    AVOID criteria (every Beers row, condition-gated STOPP rows) match on drug presence (+ a
    case-insensitive substring match against a supplied free-text condition when condition-gated);
    START criteria match on drug **absence** given a matching condition.
  - Discrepancy classification engine (`app/medication/discrepancy.py`, deterministic, no LLM) —
    RxCUI-first, normalized-name-fallback diff between two independently parsed/normalized
    medication lists, producing `added`/`omitted`/`dose_changed`/`frequency_changed` findings.
  - Guardrailed LLM narrative (`app/medication/explanation_guardrail.py`, ADR-0020) — one batched
    call (not one per finding) proposes a plain-language narrative for every PIP/discrepancy finding
    from that finding's own structured rule-output; a deterministic post-generation check
    (`check_narrative_grounded`) discards any narrative introducing a medication name outside the
    finding's own set, a number absent from the finding's own data, an escalation/severity word, or
    an unlicensed clinical-directive phrase not already in the finding's own explanation. Scoped to
    Phase 3 finding types only — Phase 1/2 `explanation` fields are already deterministic strings
    with nothing for a guardrail to check, so retrofitting it there would touch already-shipped,
    already-tested code for no safety benefit. Degrades silently (no narrative, not an error) when
    no provider is available or the budget is exhausted; the deterministic `explanation` is always
    shown regardless.
  - API: `age_years` alone (independent of the four renal-only fields) now triggers PIP screening;
    a new `conditions[]` field supplies free-text diagnoses; a new `previous_raw_text` field
    triggers discrepancy classification against `raw_text`. Three new SSE events on the same stream:
    `previous_medication`, `pip`, `discrepancy`.
  - Frontend: PIP-screening and previous-medication-list input sections, `PipFindingCard`/
    `DiscrepancyFindingCard`, and a distinctly-styled (italic, sparkle icon) narrative note in the
    existing medication panel — no new page.
  - Tests written alongside each feature: golden tests for PIP screening (age gate, unconditional/
    condition-gated AVOID, START omission, case-insensitivity) and discrepancy classification
    (added/omitted/dose/frequency changes, RxCUI vs. name matching, duplicate-entry handling),
    guardrail unit tests (grounded pass, cross-drug/number/escalation/directive-phrase failures,
    degraded-mode fallback), loader tests, API tests, frontend unit/component tests, and new
    Playwright e2e coverage using reusable fixtures.
- **Blueprint reconciliation** (Roadmap Month 1 closeout): saved the master implementation
  blueprint verbatim to `docs/specifications/corveon-master-implementation-blueprint-v1.0.md` as the
  permanent in-repo reference, then closed every concrete gap the reconciliation against the current
  repository found:
  - Chat deletion (`DELETE /api/v1/chats/{id}`) now collects its documents' object-storage keys
    before deleting the row, writes one `audit_log` entry for the `chat.delete` action (entity_id,
    document_count — never content), and enqueues a new fire-and-forget ARQ job
    (`delete_storage_objects`) to clean up the corresponding blobs after the DB rows are gone
    (blueprint §23.6). Previously only the DB-level `ON DELETE CASCADE` ran; storage was orphaned
    and the deletion itself wasn't audited.
  - A background embedding-reindex job (`app/workers/tasks.py::reindex_chat_chunks`, blueprint
    §23.4) — idempotent and resumable via a new `ChunkRepository.list_chunks_missing_embedding`
    query, embedding only chunks that don't yet have a row under the target `model_id` rather than
    mixing or overwriting. Triggered per-chat (`chat_id` + `user_id`, matching the RLS-scoping
    pattern every other worker task uses); a system-wide "reindex every chat" admin trigger is
    deferred — it would need an admin RBAC-gated endpoint and a superuser/bypass-RLS DB session
    pattern, neither of which exists yet anywhere in this codebase (the `/audit` admin endpoint is
    similarly not yet built), so faking one just for this would be a bigger, riskier addition than
    the blueprint's one-sentence requirement asks for.
  - `infra/docker-compose.yml` gains `api` and `worker` services building the same production image
    (`infra/docker/backend.Dockerfile`) the CI/deploy path uses, differing only in command
    (blueprint §17/§19: "docker-compose for local (api, worker, postgres, redis, ollama)"). Running
    the backend directly on the host remains the faster inner loop for active development; this is
    for a full from-scratch stack and for parity-testing the production image before deploy.
  - Query Understanding, Task Planning, and Retrieval — previously three functions inside
    `app/orchestrator/chat_orchestrator.py` — are now `Agent` protocol implementations
    (`app/agents/base.py::Agent`, blueprint §7) over a shared `OrchestratorState`
    (`app/agents/state.py`) in `app/agents/{query_understanding,task_planning,retrieval}.py`. Pure
    refactor, no behavior change (same 35 orchestrator tests pass, rewritten to construct
    `OrchestratorState` and call `TaskPlanningAgent().run()` directly). `app/agents/` was an empty
    scaffold before this; a real agent (Evidence Verification, Medication-Safety Analysis, etc.,
    once their subsystems land Month 3+) is now one more file here implementing the same protocol,
    not a redesign of the two agents already wired in.
  - OCR is now its own ingestion progress stage (`app/workers/tasks.py::_extract_stage_for`,
    blueprint §12) for image uploads (`image/png`, `image/jpeg`), which always go through OCR and so
    can announce it upfront; a PDF's page-by-page OCR fallback stays labeled `extracting` since
    that's decided mid-parse, not knowable in advance. `docs/DEVELOPER.md`'s blueprint-listed
    `Uploading`/`Cleaning text`/`Verifying content`/`Preparing response` stages were deliberately
    **not** added — `Uploading` already happens synchronously before the job starts, there is no
    distinct text-cleaning step to label honestly, and `Verifying content`/`Preparing response` are
    Evidence Engine concepts that don't exist yet; a stage label with no real work behind it would
    be exactly the kind of half-finished implementation CLAUDE.md rules out.

### Added
- **Auth + Users** (Roadmap Week 1, first slice): registration, login, refresh, logout, and profile
  lookup, with Argon2id password hashing, JWT access/refresh tokens, and Redis-backed refresh-token
  revocation.
- Data layer: async SQLAlchemy 2.0 engine/session, `organizations` + `users` models and repository,
  and the baseline Alembic migration (`0001_baseline_organizations_and_users`) — verified against a
  live Postgres with a clean autogenerate empty-diff and a full downgrade/upgrade round trip
  (ADR-0002).
- Core cross-cutting infrastructure: typed `Settings` (pydantic-settings, matching
  `docs/ENVIRONMENT.md`), structlog JSON/console logging wired through stdlib with `trace_id`
  propagation, OpenTelemetry FastAPI instrumentation, Prometheus `/metrics`, and a uniform
  `{error_code, message, details, trace_id}` error model.
- `GET /api/v1/auth/me` — a small, additive endpoint (not in the original catalog) so the frontend
  can fetch the authenticated user's profile; `/login` only returns tokens. Documented in
  [docs/API.md](docs/API.md).
- Frontend app shell: Next.js 16 App Router layout, light/dark theme (flash-free, per Next's
  documented pattern), TanStack Query provider, Tailwind design tokens (incl. the five evidence
  source-class colors, ready for the Evidence feature).
- Frontend auth: login/register pages, a secure httpOnly-cookie session via Next.js Route Handlers
  proxying the backend (`ADR-0012`), presence-based route guarding (`proxy.ts`, Next 16's renamed
  `middleware.ts`), and a minimal authenticated dashboard landing page.
- Tests: backend unit/api/database/security suites (pytest); frontend unit tests (Vitest, 12
  passing) and Playwright e2e/a11y specs for the auth flow (not yet wired into CI — full-stack
  orchestration is tracked as a follow-up).
- [ADR-0012](docs/adr/0012-frontend-auth-cookie-bff-proxy.md): httpOnly-cookie BFF proxy for
  frontend auth; explicitly defers the SSE-authorization bridge to the Chat feature (interacts
  with ADR-0007).
- **Chat CRUD with per-chat isolation** (Roadmap Week 1): create/list/get/rename/pin/archive/
  delete, with search and pinned/archived filtering. Isolation is triple-enforced — the repository
  layer, and genuine Postgres Row-Level Security verified with a dedicated cross-user bypass-
  attempt test (not just an app-layer check) — see [ADR-0013](docs/adr/0013-postgres-rls-requires-nonsuperuser-app-role.md).
- Frontend: a searchable/filterable chat list, a chat detail page (inline rename, pin/archive/
  delete), and a dashboard recent-chats preview, all proxied through the same Next.js Route
  Handler / httpOnly-cookie pattern as auth (ADR-0012). Distinctive editorial typography (Fraunces
  display font) and Framer Motion list transitions.
- Tests: backend api/database/security suites for chats, including a raw-SQL RLS enforcement test
  independent of application code; frontend unit tests (22 passing) and Playwright e2e/a11y specs.
  A genuine query-cache bug was found via live browser testing and fixed with a dedicated
  regression test — see "Fixed" below.
- **SSE-streaming grounded chat, PDF upload/ingestion, and pgvector semantic search** (Roadmap
  Week 1): `messages`, `documents`, `document_chunks`, `chunk_embeddings`, and `jobs` tables
  (migration `0003`), each with the same triple-enforced per-chat isolation as chats — including
  genuine Postgres RLS via a correlated `EXISTS` against `chats` (these tables carry `chat_id`, not
  `user_id`, directly) — see [ADR-0015](docs/adr/0015-hnsw-index-via-raw-migration-ddl.md) for the
  HNSW-index/autogenerate interaction this surfaced.
- Provider-agnostic AI layer (`app/providers/`): Gemini and Ollama streaming adapters (plain httpx,
  no SDK), selected by a priority-ordered registry (ADR-0006) — a mid-stream provider failure is
  never spliced with a different provider's continuation (would garble the response); a
  configured-but-unreachable provider fails over silently before any output, and no provider at
  all degrades to a typed `provider_unavailable` result, never a hard error.
- Ingestion pipeline (`app/ingestion/`, `app/workers/`): PDF parsing (PyMuPDF, page-count capped
  against PDF-bombs), paragraph-aware chunking with overlap, local embeddings
  (`sentence-transformers`, BGE query-prefix convention, L2-normalized for cosine search) — all run
  in an ARQ worker (ADR-0011), never inline in the request, with per-stage progress
  (`validating → extracting → chunking → embedding → indexing → complete`) polled by a job-events
  SSE endpoint.
- A minimal orchestrator (`app/orchestrator/chat_orchestrator.py`) — explicitly the Week 1
  fast-path/RAG-grounded slice (CLAUDE.md §23.5), not the full routing-policy state graph
  (ADR-0003, Month 1+): retrieves this chat's own document chunks only when any exist, grounds the
  system prompt in them with inline citations, and persists every assistant reply with a
  `routing_trace` recording the path taken, provider used, and retrieved chunks — no fabricated
  confidence scores or source-verification claims belong to this slice.
- [ADR-0016](docs/adr/0016-sse-stream-ticket-bridge.md): resolves the SSE-authorization bridge
  ADR-0012 deferred — a 60-second stream ticket lets the browser open the two direct-to-backend SSE
  connections (chat streaming, job progress) without ever exposing the real session-backing access
  token in a URL.
- [ADR-0014](docs/adr/0014-local-disk-storage-fallback.md): local-disk object storage fallback when
  R2 is unconfigured, mirroring ADR-0006's absence-is-normal posture for AI providers.
- Frontend: a message thread with streaming token-by-token reveal, inline citation chips for
  grounded answers, a document upload panel with live per-file ingestion progress, and an honest
  degraded-mode banner when no AI provider is reachable — all on the chat detail page, replacing
  the earlier "messaging is coming soon" placeholder.
- Tests: backend unit (chunking, PDF parsing against in-memory-generated PDFs, embeddings against
  the real model, provider adapters against `httpx.MockTransport`, registry failover semantics),
  api (full upload → ARQ-ingestion → search → grounded-chat flow), database (RLS proofs for all
  five new tables), and security suites; frontend unit tests (Vitest) and Playwright e2e/a11y specs
  verified against a live backend + browser, not just structurally.
- A full-stack **`e2e` CI job** ([.github/workflows/ci.yml](.github/workflows/ci.yml)): stands up
  Postgres+pgvector and Redis service containers, applies migrations, starts the FastAPI backend
  and the ARQ worker, then runs the entire Playwright `tests/e2e` + `tests/a11y` suite against
  Playwright's own built `next build && next start`. Closes the Week 1 roadmap item that previously
  left e2e/a11y written but not CI-gated.
- **Provider infrastructure hardening** (Roadmap Month 1, Phase 1): a per-provider circuit breaker
  (`app/providers/health.py`) skips a repeatedly-failing provider for a cooldown window instead of
  retrying it every request; a per-provider token-bucket rate limiter and a per-request
  `LLMCallBudget` (`app/providers/budget.py`, CLAUDE.md §23.2) cap concurrent-request RPM and a
  single request's total provider-call fan-out respectively; provider-call Prometheus metrics and
  structured logs (`app/providers/metrics.py`) record every attempt, skip, success, and failure by
  provider. All wired into `ProviderRegistry`/`build_provider_registry` and threaded through
  `chat_orchestrator.stream_response` and the messages endpoint — the "absence of a provider is
  never an error" posture (ADR-0006) is unchanged: health/rate-limit state is only ever consulted
  for providers that are already configured. New settings (`GEMINI_RPM_LIMIT`,
  `ANTHROPIC_RPM_LIMIT`, `OPENAI_RPM_LIMIT`, `OPENROUTER_RPM_LIMIT`, `OLLAMA_RPM_LIMIT`,
  `PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD`, `PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS`)
  documented in `.env.example`/`docs/ENVIRONMENT.md`. 22 new unit tests.
- **Anthropic, OpenAI, and OpenRouter provider adapters** (Roadmap Month 1, Phase 2): an
  `AnthropicProvider` (`app/providers/anthropic.py`) against the Messages API (SSE
  `content_block_delta` events, top-level `system` field, required `max_tokens`, `x-api-key`
  header) — genuinely different wire format from the OpenAI shape, so it gets its own adapter. An
  `OpenAIProvider` and `OpenRouterProvider` share a new `OpenAICompatibleProvider` base
  (`app/providers/openai_compatible.py`) — both expose the identical Chat Completions wire shape,
  so the SSE-parsing/key-rotation logic lives once, keyed by `base_url`. All three wired into
  `build_provider_registry()`, registered only when their key pool is configured (unconfigured
  providers still never appear in the registry, ADR-0006), with their own token-bucket rate limits
  when `*_RPM_LIMIT` is set. 14 new unit tests against `httpx.MockTransport`.
- **Production routing policy** (Roadmap Month 1, Phase 3): the Week 1 binary fast-path/RAG router
  is replaced with a 4-way routing policy (`RoutingPath`: `fast_path` / `pure_llm` / `rag_grounded`
  / `rag_no_match`) built from two explicit steps in `app/orchestrator/chat_orchestrator.py` —
  Query Understanding (`classify_intent`, a deterministic trivial-input allow-list rather than an
  LLM call, since spending a provider round-trip just to classify would defeat the point of a
  *low-latency* fast-path) and Task Planning (`_plan_task`, which combines that classification with
  whether the chat has documents and whether retrieval actually found anything relevant). The
  `routing_trace` now distinguishes "no documents to ground on" from "documents exist but none
  matched," which the old binary path collapsed into one bucket. All Week 1 behavior is preserved
  (existing API tests pass unchanged); the four remaining blueprint routing branches (public
  evidence, org-trusted sources, multi-agent verification, external lookup) plug in as new steps in
  this same pipeline once Month 3/6-12 build the subsystems they depend on. New unit tests in
  `tests/unit/test_chat_orchestrator.py`.
- **Multi-format ingestion** (Roadmap Month 1, Phase 4): `app/ingestion/parsing.py` gains
  `parse_docx`, `parse_pptx`, `parse_markdown`, and `parse_image` (Tesseract OCR), plus a scanned-
  page OCR fallback inside `parse_pdf` — a PDF page with no extractable text is rendered to an
  image and OCR'd rather than silently dropped. A MIME-keyed `parse_document` registry is the
  single dispatch point both the upload endpoint and the ARQ worker go through. The upload
  endpoint's validation is reworked: the canonical MIME type (and storage-key extension) is now
  derived from the file extension rather than trusted from the client's `Content-Type` header
  (inconsistent across browsers, especially for `.md`), checked against per-format magic bytes
  (DOCX/PPTX/PNG/JPEG) or UTF-8 decodability (Markdown). `.docx`/`.pptx`/`.md`/`.markdown`/`.png`/
  `.jpg`/`.jpeg` join `.pdf` as accepted uploads, both in the API and the frontend file picker
  (button relabeled "Upload PDF" → "Upload document"). CI gains a `tesseract-ocr` apt-get install
  step in both the backend and e2e jobs — OCR tests need the real binary, not just the
  `pytesseract` Python wrapper. `ocrmypdf` remains a declared-but-unused dependency; direct
  PyMuPDF-render + Tesseract was sufficient for this scope and avoids subprocess/temp-file
  complexity — documented in `app/ingestion/parsing.py` as a deliberate scoping choice, revisit if
  OCR quality demands it. New unit tests in `tests/unit/test_parsing.py` plus new API-level
  DOCX/Markdown full-pipeline tests in `tests/api/test_documents_api.py`.
- **Export system** (Roadmap Month 1, Phase 5): `app/export/message_export.py` renders a message
  to Markdown (raw UTF-8, lossless) or PDF (fpdf2, core Latin-1 font), preserving its citations
  (`routing_trace.retrieved_chunks`) and metadata (role, timestamp, routing path/provider/status).
  PDF has no bundled Unicode font — a small transliteration table covers common clinical symbols
  (µ, °, ±, smart quotes/dashes) and anything else out of range becomes a visible `[?]` rather than
  a silently-wrong character, a real concern on a clinical platform. New synchronous endpoint
  `POST /api/v1/chats/{id}/messages/{mid}/export {format: md|pdf}` (matches the documented `200`
  file contract — not an ARQ job) plus `MessageRepository.get_by_id_for_chat`. `fpdf2` promoted
  from a transitive dependency (via `ocrmypdf`) to a direct one. Frontend gains a matching BFF
  route (`app/api/chats/[chatId]/messages/[messageId]/export/route.ts`, cookie-authenticated —
  not the SSE stream-ticket bridge, which is for streaming only) and export buttons on assistant
  message bubbles.
- **Observability — audit logging + distributed tracing** (Roadmap Month 1, Phase 6): an
  append-only `audit_log` table (migration `0004`) — `actor_id`, `action`, `entity_type`,
  `entity_id`, `ip`, and a JSONB `metadata` column (mapped from a Python `audit_metadata` attribute
  to avoid colliding with SQLAlchemy's reserved `metadata` name) — written via a new
  `AuditLogRepository` from every sensitive action CLAUDE.md §8 names: auth register/login/logout
  and document upload/delete (already existing endpoints) plus the new message-export endpoint.
  There is no admin-facing read endpoint yet, so `tests/database/test_audit_log.py` verifies rows
  by querying the table directly — the honest ground truth for what exists today. Also adds
  per-attempt OTel spans around each provider call (`provider.stream_chat`, recording
  `provider.name`/`provider.outcome` and exceptions) and around orchestrator task planning and
  response generation (`orchestrator.plan_task`, `orchestrator.generate_response`), alongside the
  Prometheus counters/histograms and structlog `trace_id` propagation already in place since Week 1.
  Grafana dashboards and Sentry are intentionally not wired up yet — there is no deployed
  environment for either to point at.
- **Expanded test matrix** (Roadmap Month 1, Phase 7): activates the two test layers
  `docs/DEVELOPER.md` had declared but never wired — `schemathesis` and `locust` were dev
  dependencies with zero tests exercising them. New CI job `contract` starts a live backend (same
  pattern as the `e2e` job) and runs: (1) `schemathesis run` — property-based fuzzing against the
  live OpenAPI schema, deliberately scoped to the `not_a_server_error` check only. Schemathesis's
  in-process pytest integration (`schemathesis.pytest.from_fixture` + ASGI transport) was tried
  first and hung indefinitely even at schema-collection time against this async FastAPI/asyncpg
  stack; the CLI against a real running server (`schemathesis run <url>/openapi.json`) is the
  stable path and is what's wired in. Broader built-in checks (`status_code_conformance` etc.) were
  evaluated and excluded — most of this API's routes correctly return 401/404/422 for cases the
  auto-generated OpenAPI metadata doesn't enumerate, which those checks treat as failures; that's a
  documentation-completeness gap across ~20 endpoints, not a contract violation, and fixing it is
  its own bounded follow-up. (2) A Locust concurrency smoke (`tests/performance/locustfile.py`,
  `ChatUser`) covering register/login/list-chats/create-chat/list-messages — asserts zero request
  failures under 5 concurrent users, not a latency threshold (shared CI runners don't give
  reproducible latency numbers); run it locally for real throughput/latency figures.

### Added
- **Evidence Verification Engine** (Roadmap Month 3): given one existing message, extracts its
  independently-verifiable claims and checks each against real medical evidence, end to end —
  `POST /chats/{id}/verify` (SSE, streams one scored claim at a time as it completes). Strictly
  scoped to the explicit Month 3 checklist (evidence engine, six public connectors, retrieval,
  provenance, confidence scoring, conflict/misinformation detection, citation verification, API,
  frontend UI, tests, docs) — org-trusted sources and premium analytics/dashboards are deliberately
  out of scope for this phase; see [docs/ROADMAP.md](docs/ROADMAP.md) Month 3 for the full
  done/deferred breakdown.
  - Data model: `evidence_verifications` / `evidence_claims` / `evidence_citations` (migration
    `0005`), every table chat_id-anchored with the same triple-enforced isolation (app guard +
    Postgres RLS + repository invariant) as every other content table.
  - Six connectors (`app/evidence/connectors/`) — PubMed, DailyMed, openFDA, ClinicalTrials.gov,
    MeSH, RxNorm — each a plain-httpx client behind a common `EvidenceConnector` protocol,
    cache-first via Redis ([ADR-0017](docs/adr/0017-evidence-cache-via-redis-not-postgres-table.md),
    chosen over the blueprint's alternative Postgres `external_cache` table) and rate-limited with
    Month 1's `TokenBucket` reused unmodified; a connector returns `[]` rather than raising on a
    not-found/rate-limited/unreachable condition, so one source's outage never breaks the others.
  - Retrieval layer merges those six connectors with this chat's own uploaded-document chunks,
    reusing Month 1's `ChunkRepository`/`EmbeddingModel` RAG primitives at the same relevance
    threshold — `app/agents/retrieval.py` itself is untouched, only its constants are imported.
  - Claim extraction and per-claim stance analysis (`app/evidence/claim_extraction.py`,
    `app/evidence/analysis.py`) each make exactly one LLM call through the existing provider
    registry/`LLMCallBudget` (no new rate-limiting abstraction) — analysis compares a claim against
    every retrieved excerpt in one call, not one call per citation, so a multi-claim verification
    stays within the existing per-request budget. Each excerpt gets a three-way stance (supports /
    contradicts / irrelevant), not a boolean — the distinction genuine conflict detection needs (a
    claim with nine irrelevant excerpts and one contradicting one is unsupported, not conflicting).
  - Deterministic source classification and confidence scoring (`app/evidence/scoring.py`, no LLM) —
    five source classes, and a 0–100 score that's an additive, documented composite of source-class
    weight + independent-source agreement + recency + citation-resolution rate, always
    reconstructable from its own rationale string.
  - Fabricated-citation guard (`app/evidence/citation_verification.py`): structurally prevented by
    construction (citations only ever come from a connector's real parsed API response, never
    LLM-generated text) plus a narrower structural-completeness check — an incomplete citation is
    flagged, not shown, per CLAUDE.md's golden rule. Uploaded-document evidence resolves by
    identifier alone (no external URL exists for the chat's own document chunks); external-source
    evidence needs both an identifier and a URL.
  - `POST /chats/{id}/verify` (`app/api/routers/evidence.py`) — 202 + SSE, same shape and stream-
    ticket bridge (ADR-0016) as `POST /chats/{id}/messages`: a `claim` event per completed claim, a
    final `done` event, or an `error` event on a degraded-mode condition. Audit-logged
    (`evidence.verify`) like every other sensitive action CLAUDE.md §8 names.
  - Not built as an `app.agents.base.Agent` — that protocol's shared `OrchestratorState` is shaped
    around the single-query message-send pipeline; this pipeline runs per-claim in a loop with
    incremental persistence and its own DB-session lifecycle, different enough to force-fitting it
    would distort the existing type rather than reuse it. Documented in
    `app/evidence/verification_service.py`'s own module docstring as a deliberate choice.
  - Frontend: a "Verify claims" trigger on assistant messages
    (`components/chats/evidence-verification-panel.tsx`) streaming claims in with a source-class
    badge (the five `evidence-*` design tokens reserved since Week 1), a confidence meter, detection
    flags, and linked citations — reuses the same stream-ticket SSE pattern
    `lib/api/messages.ts`/`use-messages.ts` established.
  - Tests written alongside each feature: backend unit (connectors against `httpx.MockTransport` +
    real Redis; claim extraction, stance analysis, scoring, citation verification; the full
    verification-service pipeline, mocking only the DB-touching repositories — the same
    `AsyncMock(spec=...)` convention `tests/unit/test_chat_orchestrator.py` already uses), API (the
    full `/verify` SSE round trip, happy path and degraded mode), and database (RLS isolation for
    all three new tables); frontend unit/hook/component tests plus a live browser verification
    against the real running backend (real ticket mint + SSE round trip, degraded-mode rendering
    confirmed end to end).

### Fixed
- `is_citation_resolved` required both an `identifier` and a `url` to consider a citation resolved,
  but uploaded-document evidence always has `url=None` (a chat's own PDF/DOCX chunk has no external
  URL to resolve to) — meaning `SourceClass.UPLOADED_DOCUMENT` claims could never actually surface a
  citation, a dead path rather than the intentional gap `SourceClass.ORG_TRUSTED` is. Caught while
  writing the verification-service tests, before merge. Fixed: uploaded-document evidence now
  resolves by identifier alone; external-source evidence is unchanged (still needs both).

### Fixed
- `.dockerignore` excluded `**/.venv` and `**/venv` but not a differently-named local venv
  (`.venv312`) — the same gap `.gitignore` had before it was fixed earlier this session. Building
  the `infra/docker-compose.yml` `api` service uploaded a 1.5GB build context (the venv) before
  failing; fixed by adding `**/.venv*`, matching the `.gitignore` fix's pattern.
- Seven `.env.example` variables had an empty default value followed by a trailing comment on the
  same line (`OLLAMA_RPM_LIMIT=                       # local inference — unlimited by default`).
  python-dotenv (used when running the backend directly on the host) strips that trailing comment
  correctly; Docker Compose's `env_file` parser does not when the value portion is empty — it took
  the literal comment text as the value. For `GEMINI_API_KEYS` this meant an unconfigured provider
  looking configured (breaking ADR-0006's "absence of a provider is never registered" contract) with
  garbage keys; for `OLLAMA_RPM_LIMIT` (typed `int | None`) it meant `pydantic-settings` rejecting
  the value outright and the `api`/`worker` containers failing to start entirely. Found by actually
  building the new `api` service, not by inspection. Fixed by moving each trailing comment to its
  own line above the (now-clean) `KEY=`.

### Fixed
- The `frontend` CI job's "Detect Next app" step checked for `frontend/next.config.mjs` etc., but
  that job's `defaults.run.working-directory` is already `frontend` — the doubled
  `frontend/frontend/...` path never existed, so `has_app` was always `false` and every frontend
  gate (lint, typecheck, Vitest, build) had been silently skipped since the Next app scaffold
  landed, with the job still showing green. Found while investigating why the frontend job
  consistently finished in ~5s. Fixed by making the paths relative to the step's actual working
  directory.
- `EmptyState` hardcoded `<h3>` for its title, which is only correct one specific place it's used
  (nested under the dashboard's "Recent chats" `CardTitle`, itself an `<h2>`) — everywhere else
  (the chats list page, both empty states on the chat detail page) it sits directly under the
  page's own `<h1>` with no `<h2>` between, an axe `heading-order` violation. Flagged as a known
  pre-existing issue in this PR's original description but left unfixed because axe wasn't wired
  into CI yet; surfaced as a real CI failure once Phase 7 actually ran it on every PR. Fixed by
  giving `EmptyState` an `as` prop (same pattern as `CardTitle`) defaulting to `h2`, with the
  dashboard usage passing `as="h3"` explicitly.
- `validation_error_handler` (`app/core/errors.py`) could itself raise while building a 422
  response: Pydantic v2's `ValidationError.errors()` embeds the raw exception instance in
  `ctx["error"]` for certain validators (here, FastAPI's own `UploadFile`-vs-plain-field type
  coercion), and that's not JSON-serializable — `JSONResponse.render()` then crashed with
  `TypeError: Object of type ValueError is not JSON serializable`, turning what should have been a
  clean 422 into an unrelated 500. Found by the new schemathesis contract job fuzzing document
  upload with a `file` multipart field sent without a filename (which decodes to a plain string,
  not an `UploadFile`). Fixed by dropping `ctx` (internal debug context, not meant for API
  consumers) from each error dict and routing the rest through `jsonable_encoder` for defense in
  depth; regression test in `tests/api/test_documents_api.py`.
- fpdf2's `multi_cell` leaves the text cursor at the end of the last line by default rather than
  resetting it to the left margin — a second `multi_cell` call then computed almost zero available
  width and raised `FPDFException: Not enough horizontal space to render a single character`.
  Caught by the new export tests, not manual testing. Fixed with a small `_write_paragraph` helper
  that always passes `new_x=XPos.LMARGIN, new_y=YPos.NEXT` explicitly.
- The frontend's `RoutingTrace` TypeScript type still only listed the Week 1 binary
  `'fast_path' | 'rag_grounded'` path and `'ok' | 'provider_unavailable'` status — stale since the
  Month 1 Phase 1 (`budget_exceeded`) and Phase 3 (`pure_llm`, `rag_no_match`) backend changes.
  Caught while wiring the export UI, not by a type error (the field is read loosely as a string in
  most places) — fixed to match the backend's actual `RoutingPath`/status values.

### Fixed
- `ChatList`'s empty state rendered its own "New chat" button directly beneath the page header's
  persistent "New chat" button — the same action offered twice on screen, which also gave two
  interactive elements an identical accessible name. Removed the redundant empty-state action.
- The chat-title rename `<Input>` had no accessible label at all (an unlabeled form control);
  added `aria-label="Chat title"`.
- The login and register pages had no `<h1>` — `CardTitle` always rendered `<h2>` (correct for a
  card that's a subsection of a page with its own heading, e.g. the dashboard's "Recent chats"),
  but wrong where the card *is* the page's only heading. Added an `as` prop to `CardTitle` and set
  `as="h1"` on the auth forms.
- Several Playwright e2e specs used locators that were ambiguous but had gone undetected: `getByText(email)`
  matched both the app-shell nav and the dashboard heading; `getByRole('alert')` matched both the
  login error and Next.js's own route announcer; `getByText(<chat title>)` matched both a chat's
  visible title and its own (hidden, closed) delete-confirmation dialog description repeating that
  title; `page.locator('main input')` matched both the rename input and a hidden file-upload input.
  Scoped each to a specific role/label instead.
- Two e2e tests read `page.url()` or navigated immediately after a client-side action without
  waiting for the resulting navigation/redirect to actually land, occasionally racing the still-
  mounted previous page (a register-then-login test filling login fields into stale register-form
  inputs; a cross-user chat-isolation test capturing the `/chats` list URL instead of the new
  chat's URL). Added the same `await expect(page).toHaveURL(...)` wait already used elsewhere.
- `useUpdateChat`'s optimistic-update cache write matched query keys by the bare `['chats']`
  prefix, which also matched the single-object chat-detail cache entry; calling `.map()` on that
  non-array entry threw inside `onMutate`, silently aborting every rename/pin/archive mutation
  before it ever reached the network (no console error, no visible failure — just no-op). Caught
  via live browser testing, not by the initial unit tests. Fixed by scoping the array-shaped
  cache write to a dedicated `['chats','list']` key, and added a regression test that seeds both
  cache shapes simultaneously.
- The RLS GUC (`set_config(..., true)`) is transaction-local: any code path committing more than
  once on the same RLS-scoped session (the ingestion pipeline's per-stage commits; the
  streaming-message endpoint's persist-user-message-then-stream flow) silently lost RLS scoping
  after the first commit, causing spurious `new row violates row-level security policy` errors or
  (worse) `StaleDataError`s from UPDATEs RLS silently filtered to zero rows. Fixed with a shared
  `commit_and_reapply_rls()` helper (`app/data/rls.py`) used everywhere a session commits more than
  once; caught by the feature's own integration tests before merge, not in production.
- `EventSourceResponse` returned directly from a route handler ignores the route decorator's
  `status_code=` — the messages endpoint was silently returning `200` instead of the documented
  `202` until the response's own `status_code` was set explicitly.
- Found via a new a11y check on the chat detail page: no `<h1>` at all (the chat title was a plain
  button, not a heading) — fixed by wrapping it in a semantic `<h1>`.

## [0.0.0] — 2026-07-07

Engineering foundation. No application code; this release establishes the structure, standards,
documentation, and CI on which all features are built.

### Added
- Repository structure: `backend/`, `frontend/`, `infra/`, `data/`, `docs/`, `.github/`
  (per [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §9).
- Engineering contract [`CLAUDE.md`](CLAUDE.md) and the full documentation set under `docs/`
  (ARCHITECTURE, DEVELOPER, SETUP, API, ENVIRONMENT, DEPLOYMENT, DEBUGGING, SECURITY,
  CONTRIBUTING, ROADMAP).
- Eleven Architecture Decision Records under [docs/adr/](docs/adr/) capturing every resolved
  decision (pgvector, forward-only migrations, custom orchestrator, DDInter, dual renal equations,
  provider-agnostic registry, backend-served SSE, embedding-model versioning, the name, the
  license, and ARQ).
- Backend packaging and tooling standards (`backend/pyproject.toml`: ruff, mypy-strict, pytest);
  frontend packaging (`frontend/package.json`, `tsconfig.json`, Prettier).
- Continuous integration ([.github/workflows/ci.yml](.github/workflows/ci.yml)) with backend and
  frontend quality gates; the frontend gates self-activate once the Next app scaffold lands.
- Local development infrastructure: `infra/docker-compose.yml`, multi-stage
  `infra/docker/backend.Dockerfile`, `Makefile`, and a fully documented `.env.example`.
- Community health files: `CODE_OF_CONDUCT.md`, `CONTRIBUTING`, `SECURITY`, issue templates,
  `CODEOWNERS`, and Dependabot configuration.
- `Apache-2.0` license and `NOTICE`.

[Unreleased]: https://github.com/kanwa2006/Corveon/compare/v0.0.0...HEAD
[0.0.0]: https://github.com/kanwa2006/Corveon/releases/tag/v0.0.0
