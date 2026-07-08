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
  delete, an honest "messaging is coming soon" empty state), and a dashboard recent-chats preview,
  all proxied through the same Next.js Route Handler / httpOnly-cookie pattern as auth (ADR-0012).
  Distinctive editorial typography (Fraunces display font) and Framer Motion list transitions.
- Tests: backend api/database/security suites for chats, including a raw-SQL RLS enforcement test
  independent of application code; frontend unit tests (22 passing) and Playwright e2e/a11y specs.
  A genuine query-cache bug was found via live browser testing and fixed with a dedicated
  regression test — see "Fixed" below.

### Fixed
- `useUpdateChat`'s optimistic-update cache write matched query keys by the bare `['chats']`
  prefix, which also matched the single-object chat-detail cache entry; calling `.map()` on that
  non-array entry threw inside `onMutate`, silently aborting every rename/pin/archive mutation
  before it ever reached the network (no console error, no visible failure — just no-op). Caught
  via live browser testing, not by the initial unit tests. Fixed by scoping the array-shaped
  cache write to a dedicated `['chats','list']` key, and added a regression test that seeds both
  cache shapes simultaneously.

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
