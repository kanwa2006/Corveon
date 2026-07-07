<h1 align="center">Corveon</h1>

<p align="center">
  <em>An open-source, provider-agnostic clinical intelligence platform that treats every
  uploaded document as potentially unreliable — and grounds every important answer in
  transparent, multi-source medical evidence.</em>
</p>

<p align="center">
  <a href="#status"><img alt="status" src="https://img.shields.io/badge/status-foundation-blue"></a>
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-Apache--2.0-green"></a>
  <img alt="python" src="https://img.shields.io/badge/python-3.12-3776AB">
  <img alt="node" src="https://img.shields.io/badge/node-20%2B%20(24%20LTS)-339933">
</p>

> ⚕️ **Not a medical device.** Corveon is a human-in-the-loop assistant for licensed
> professionals. It never replaces clinical judgment and never answers confidently on
> suspected misinformation. See [`docs/SECURITY.md`](docs/SECURITY.md) and the safety notes below.

---

## What Corveon is

A single **AI Orchestrator** decides, per request, which models, retrieval strategies, and
specialized agents to run. An **Evidence Verification Engine** cross-checks claims against trusted
public medical knowledge (openFDA, DailyMed, RxNorm/RxNav, PubMed/PMC, ClinicalTrials.gov, MeSH)
and organization-defined trusted corpora. A **deterministic Medication-Safety Engine** performs
RxNorm normalization, drug–drug interaction detection, renal/dose checks, and STOPP/START/Beers
screening — where the **rules engine is the source of truth** and the LLM only parses input and
explains rule outputs.

Where a typical RAG app *always* retrieves, Corveon decides *when not to*. Where a typical app
trusts its inputs, Corveon assumes every document may be wrong and shows its evidence.

### Defining properties
- **Evidence before response** — every important statement is tagged with one of five provenance
  classes (uploaded doc · verified public · org-trusted · AI reasoning · conflicting/insufficient)
  and a transparent 0–100 confidence score.
- **Provider-agnostic** — Gemini, Claude, OpenAI, OpenRouter, and local Ollama plug in via config.
  Zero providers configured is a *valid* state; the platform degrades gracefully to deterministic,
  non-LLM features (see [ADR-0006](docs/adr/0006-provider-agnostic-plugin-registry.md)).
- **Absolute per-chat isolation** — no cross-chat or global memory; enforced app-side, by Postgres
  RLS, and by a repository invariant.
- **Deterministic where it matters** — medication safety is a rules engine, not a prompt.
- **Fully observable** — OpenTelemetry spans per agent and provider, structured logs, health checks.

## Tech stack (see [ADR log](docs/adr/) for the "why")

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python 3.12), Uvicorn, SQLAlchemy 2.0 async, Alembic |
| Async | ARQ workers on Redis |
| Data | PostgreSQL 16 + pgvector (HNSW, `vector(384)`), Redis, Cloudflare R2 |
| AI | Custom typed orchestrator; provider-agnostic layer; sentence-transformers embeddings (local CPU) |
| Frontend | Next.js 16 (App Router) + React 19 + TypeScript, TanStack Query, Zustand, shadcn/ui, Tailwind |
| Observability | OpenTelemetry + Prometheus + Grafana + structlog + Sentry |
| Testing | pytest, Testcontainers, schemathesis, Vitest, Playwright, axe-core |

## Repository layout
```
backend/     FastAPI app, orchestrator, agents, providers, evidence, medication, ingestion, data, workers
frontend/    Next.js App Router, components, lib (api client / SSE / state)
infra/       Docker, docker-compose, Grafana, deploy config
data/        Pinned drug-data snapshot loaders
docs/        Architecture, developer, setup, API, environment, deployment, debugging, security, ADRs
.github/     CI/CD workflows
```
Full responsibilities: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Agent rules: [`CLAUDE.md`](CLAUDE.md).

## Quickstart (local dev)
> This repository currently contains the **engineering foundation only** (structure, standards,
> docs, CI). Application code is built incrementally per [`docs/ROADMAP.md`](docs/ROADMAP.md).

```bash
# 1. Clone and configure
git clone https://github.com/kanwa2006/Corveon.git && cd Corveon
cp .env.example .env          # fill in as needed; all AI providers are optional

# 2. Bring up local services (Postgres+pgvector, Redis, Ollama)
docker compose -f infra/docker-compose.yml up -d

# 3. Backend (Python 3.12)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# alembic upgrade head   # once migrations exist
# uvicorn app.main:app --reload

# 4. Frontend (Node 20+; 24 LTS recommended)
cd ../frontend && pnpm install && pnpm dev
```
Detailed, OS-specific instructions: [`docs/SETUP.md`](docs/SETUP.md).

## Documentation
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design, data model, request flows
- [DEVELOPER.md](docs/DEVELOPER.md) — conventions, testing, per-feature Definition of Done
- [SETUP.md](docs/SETUP.md) · [ENVIRONMENT.md](docs/ENVIRONMENT.md) · [DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [DEBUGGING.md](docs/DEBUGGING.md) — observability & the debugging workflow
- [API.md](docs/API.md) — REST + SSE contract · [SECURITY.md](docs/SECURITY.md) — threat model
- [CONTRIBUTING.md](docs/CONTRIBUTING.md) · [ROADMAP.md](docs/ROADMAP.md) · [adr/](docs/adr/) — decision records

## Contributing & community
Contributions are welcome. Start with [CONTRIBUTING.md](docs/CONTRIBUTING.md) and the engineering
contract in [CLAUDE.md](CLAUDE.md). All participants agree to the
[Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities privately per
[SECURITY.md](docs/SECURITY.md) — never in a public issue. Notable changes are tracked in
[CHANGELOG.md](CHANGELOG.md).

## Status
**Foundation established.** Structure, standards, documentation, and CI are in place; feature
implementation follows the phased roadmap. See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## License
[Apache-2.0](LICENSE). "Corveon" is an adopted project name; a formal trademark clearance is
advised before commercial launch (see [ADR-0009](docs/adr/0009-name-corveon.md)).
