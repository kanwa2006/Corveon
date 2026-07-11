# Corveon — Deployment

## Free-tier MVP topology
| Concern | Service | Notes |
|---|---|---|
| Frontend | **Vercel** (Hobby) or Cloudflare Pages | static + RSC only |
| API + workers | **Fly.io / Render** (free) | persistent process — serves **all SSE** (§23.3) |
| Postgres + pgvector | **Supabase / Neon** (free) | source of truth + vectors |
| Redis | **Upstash** (free, serverless) | cache + ARQ queue |
| Object storage | **Cloudflare R2** | S3-compatible, no egress fees |
| LLM | **Gemini free / Ollama** | providers optional; Ollama for privacy |

> **Hard rule (ADR-0007):** SSE streaming and job-event channels are served by the FastAPI backend
> on a persistent host (Fly/Render), **never** by Vercel serverless functions (execution-time caps
> break long streams). Vercel hosts only the static/RSC frontend, which opens SSE against the backend.

## Containerization
- Multi-stage production image for the backend (`infra/docker/backend.Dockerfile`).
- `infra/docker-compose.yml` for local dev (api, worker, postgres, redis, ollama).
- The **same** image runs the API (`uvicorn`/`gunicorn`) and the ARQ worker (different entrypoints).

## CI/CD (GitHub Actions)
Target pipeline gate order:
`lint → typecheck → test matrix → security scan → build image → (deploy on green)`.
Database migrations run as a **gated, explicit step** — never implicitly on deploy.

The committed skeleton (`.github/workflows/ci.yml`) implements the **quality gates today** —
backend `lint → format → typecheck → test → migrations-sync → security`, and frontend
`lint → typecheck → test → build` (which self-activates once the Next app scaffold lands). The
**image-build and deploy** stages are wired once the application entrypoints exist (Roadmap Week 1),
so the workflow never claims to deploy code that isn't there yet.

## Configuration & secrets
- 12-factor env config via `pydantic-settings`; `.env.example` documents every variable.
- Production secrets live in the platform secret manager; CI uses GitHub Actions encrypted secrets.
- No secret is ever committed or stored in the database.

## Environment promotion
`preview` (per-PR) → `staging` → `production`. Migrations are forward-only in production (ADR-0002);
roll forward with a new migration rather than downgrading.

## Path to enterprise scale (§17)
- Split ARQ workers into dedicated pools (ingest vs verify vs export).
- ✅ Vectors can move to **Qdrant past ~10M** — `VECTOR_STORE=qdrant` (ADR-0001, ADR-0022).
- ✅ Managed Postgres with a read replica — `DATABASE_READ_REPLICA_URL` (ADR-0023). RLS-based
  multi-tenancy is already the default (ADR-0013).
- Horizontal API autoscaling; per-tenant provider key pools.
- ✅ Optional on-prem / Ollama-only deployment for data-residency (hospitals) —
  `DEPLOYMENT_MODE=ollama_only` (ADR-0024). SSO/SAML remains future work.

## Pre-deploy checklist
- [ ] CI fully green (all test layers + security scans).
- [ ] Migrations reviewed; models↔migrations sync check passes.
- [ ] Required secrets present in the target environment (`JWT_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, R2).
- [ ] `/ready` returns healthy for DB, Redis, and configured providers.
- [ ] Drug-data snapshots pinned and checksum-verified where medication features are enabled.
