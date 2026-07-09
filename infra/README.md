# infra/

Deployment and local-development infrastructure.

| Path | Purpose |
|---|---|
| `docker-compose.yml` | local dev services: Postgres+pgvector, Redis, Ollama, API, ARQ worker |
| `docker/backend.Dockerfile` | multi-stage production image (API **and** ARQ worker) — `api`/`worker` in compose build this same image, differing only in command |
| `grafana/` | Grafana dashboards for the Prometheus metrics (§16) |

CI/CD lives in [`../.github/workflows/`](../.github/workflows/). Deployment topology and the
enterprise scale-up path are documented in [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md).

## Quick reference
```bash
# Full local stack (Postgres, Redis, Ollama, API, worker) — needs a repo-root
# .env file first (copy .env.example); provider keys are optional.
docker compose -f infra/docker-compose.yml up -d

# First run only: apply migrations inside the running api container.
docker compose -f infra/docker-compose.yml exec api alembic upgrade head

# Just the backing services, running the API/worker on the host instead
# (faster inner loop for active backend development):
docker compose -f infra/docker-compose.yml up -d postgres redis ollama

# Build the backend image directly (context = repo root)
docker build -f infra/docker/backend.Dockerfile -t corveon-backend .

# Run the worker from the same image
docker run --rm corveon-backend arq app.workers.main.WorkerSettings
```
