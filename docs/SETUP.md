# Corveon — Local Setup

Get a development environment running. Application code lands incrementally per
[ROADMAP.md](ROADMAP.md) — the Auth + Users slice (Week 1) is in place; chat/document/evidence/
medication routes follow.

## Prerequisites
| Tool | Version | Notes |
|---|---|---|
| Python | 3.12.x | backend |
| Node.js | ≥ 20.11 (24 LTS recommended) | frontend |
| pnpm | 9.x | `corepack enable && corepack prepare pnpm@9.12.0 --activate` |
| Docker + Compose | recent | local Postgres+pgvector, Redis, Ollama |
| Tesseract | 5.x | OCR (`apt install tesseract-ocr` / `brew install tesseract` / choco) |
| Ollama | optional | local, zero-cost LLM; the implicit default provider |

## 1. Configure
```bash
cp .env.example .env
# Set JWT_SECRET_KEY (openssl rand -hex 32). All AI provider keys are optional.
```

## 2. Local services
```bash
docker compose -f infra/docker-compose.yml up -d   # postgres(pgvector), redis, ollama
docker compose -f infra/docker-compose.yml ps
```
Postgres is exposed on `5432`, Redis on `6379`, Ollama on `11434` (see the compose file). On first
boot, an init script creates the `corveon` role/database as a non-superuser owner — required for
Row-Level Security to actually apply (ADR-0013). Init scripts only run on a **fresh** data volume:
if you have a pre-existing local Postgres volume from before this changed, run
`docker compose -f infra/docker-compose.yml down -v` once before `up -d` to let it re-initialize.

## 3. Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head                 # applies the baseline organizations/users schema
ruff check . && mypy app && pytest   # quality gates
uvicorn app.main:app --reload        # http://localhost:8000 (docs at /docs, health at /health)
```
Document uploads need the ARQ ingestion worker running too (a separate persistent process, same
as production — ADR-0011), in another terminal:
```bash
arq app.workers.main.WorkerSettings
```
First use of search/documents/messages loads the local embedding model (`EMBEDDING_MODEL_ID`,
default `BAAI/bge-small-en-v1.5`, ~130 MB) from the Hugging Face cache, downloading it once if not
already cached — this happens lazily, not at startup, so unrelated endpoints/tests never pay this
cost (see `app/ingestion/embeddings.py`).

## 4. Frontend
```bash
cd frontend
pnpm install
pnpm dev                             # http://localhost:3000
```

## 5. (Optional) Pull a local model
```bash
ollama pull llama3.1                 # or any model set in OLLAMA_DEFAULT_MODEL
```

## Windows notes
- Use PowerShell for venv activation (`.venv\Scripts\Activate.ps1`) or the Git Bash shell.
- Tesseract on Windows: install via Chocolatey (`choco install tesseract`) and ensure it is on `PATH`.
- Line endings are normalized by `.editorconfig` / `.gitattributes` to LF.

## Verifying the environment
- `GET http://localhost:8000/health` → liveness. `GET http://localhost:8000/ready` → DB + Redis checks.
- `docker compose ... logs -f postgres` → confirm pgvector extension is available.
- If a provider is unset, that is fine — the platform runs in local/degraded mode by design.
- Uploaded documents land on local disk (`backend/.data/documents`, gitignored) unless all four
  `R2_*` variables are set — a disclosed dev/test fallback, not a stub (ADR-0014).

## Troubleshooting
See [DEBUGGING.md](DEBUGGING.md). First checks: the `trace_id` in logs, provider health at
`/ready`, and the job `progress_stage` for stuck uploads.
