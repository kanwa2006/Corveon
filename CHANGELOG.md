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

### Fixed
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
