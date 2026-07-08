# Changelog

All notable changes to Corveon are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Roadmap phases that map to future releases are tracked in [docs/ROADMAP.md](docs/ROADMAP.md).

## [Unreleased]

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
