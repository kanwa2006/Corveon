# Corveon — Developer Guide

How we build. The binding checklist is [`../CLAUDE.md`](../CLAUDE.md); this expands it.

## The per-feature order (every feature, no exceptions)
**Architecture → Database → API → Backend → Frontend → Testing → Documentation.**
Validate each completed subsystem before starting the next. Never skip validation to write more
code. If a step reveals a design gap, fix the design (and its ADR/doc) before continuing.

## Coding conventions
### Backend (Python 3.12)
- Full type annotations; Pydantic v2 for all boundaries. `mypy --strict` must pass.
- Async-first (`async def`, `asyncpg`, `httpx.AsyncClient`, ARQ).
- `ruff` for lint + format (line length 100). Rulesets in `backend/pyproject.toml`.
- Small, single-responsibility modules. Routers stay thin; logic lives in services/agents.
- **Business logic never names a concrete AI provider** — always go through the registry/router.
- Validate all external input; agent outputs are schema-validated before use.

### Frontend (TypeScript)
- `strict` + `noUncheckedIndexedAccess`. ESLint + Prettier. `tsc --noEmit` must pass.
- Server state via TanStack Query; UI state via Zustand; streaming via the shared SSE hook.
- Types shared with the backend are generated from OpenAPI; do not hand-duplicate contracts.
- WCAG 2.2 AA is a requirement, not a nice-to-have (axe-core in CI).

## Testing strategy (free/open tooling)
| Layer | Tools | Scope |
|---|---|---|
| Unit | pytest, pytest-asyncio | rules engine, routing policy, pure logic |
| Integration | pytest + Testcontainers (Postgres, Redis) | DB/cache/queue |
| API contract | httpx + schemathesis | endpoint shapes, status codes, error model |
| Database | pytest + Alembic up/down | migrations, RLS/isolation invariants |
| Auth | pytest | JWT, RBAC, ownership |
| Pipeline | pytest fixtures + Synthea data | upload/OCR/chunk/embed/retrieve |
| AI pipeline | pytest + recorded provider responses (VCR-style) | routing + retrieval correctness |
| Medication | pytest **golden tests** + pinned DDInter/Beers/STOPP-START snapshots | deterministic outputs |
| Export | pytest | MD/PDF fidelity |
| Security | bandit, pip-audit + custom injection/upload-abuse tests | vuln + abuse |
| Performance | Locust | hot-path latency/throughput |
| Frontend | Vitest + React Testing Library | components |
| E2E | Playwright | full journeys |
| A11y | @axe-core/playwright | WCAG checks |

### Definition of Done (per feature)
All **relevant** layers above are green in CI before the next feature begins. Medication rules
must have golden tests. Docs updated in the same PR. New resolved decision ⇒ an ADR.

## Determinism & the LLM's role
The medication rules engine is the source of truth. The LLM only (a) parses messy input into
structured entries and (b) explains rule outputs. A post-generation guardrail strips any drug
fact, severity, or recommendation absent from the structured rule output — test this explicitly.

## Reproducibility
Drug data (DDInter 2.0, Beers 2023, STOPP/START v3, RxNorm) loads as pinned, checksummed
snapshots recorded in `drug_data_snapshots`. Golden tests pin against a specific snapshot version
so results are stable across time. See [`../data/loaders/README.md`](../data/loaders/README.md).

## Branching & commits
- Branch from `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`, `test/…`.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- One reviewable concern per PR. CI must be green. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Local quality gates (run before pushing)
```bash
# backend
cd backend && ruff check . && mypy app && pytest && bandit -q -r app && pip-audit
# frontend
cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm build
```
