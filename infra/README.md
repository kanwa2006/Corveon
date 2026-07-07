# infra/

Deployment and local-development infrastructure.

| Path | Purpose |
|---|---|
| `docker-compose.yml` | local dev services: Postgres+pgvector, Redis, Ollama |
| `docker/backend.Dockerfile` | multi-stage production image (API **and** ARQ worker) |
| `grafana/` | Grafana dashboards for the Prometheus metrics (§16) |

CI/CD lives in [`../.github/workflows/`](../.github/workflows/). Deployment topology and the
enterprise scale-up path are documented in [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md).

## Quick reference
```bash
# Local services
docker compose -f infra/docker-compose.yml up -d

# Build the backend image (context = repo root)
docker build -f infra/docker/backend.Dockerfile -t corveon-backend .

# Run the worker from the same image
docker run --rm corveon-backend arq app.workers.WorkerSettings
```
