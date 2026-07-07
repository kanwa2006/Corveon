# Corveon — Local Setup

Get a development environment running. The repo currently ships the **engineering foundation**;
application entrypoints (`app/main.py`, migrations, Next routes) are added per [ROADMAP.md](ROADMAP.md).

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
Postgres is exposed on `5432`, Redis on `6379`, Ollama on `11434` (see the compose file).

## 3. Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ruff check . && mypy app && pytest   # quality gates (green on empty scaffold)
# alembic upgrade head               # once migrations exist
# uvicorn app.main:app --reload      # once app/main.py exists → http://localhost:8000
```

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
- `GET http://localhost:8000/health` → liveness (once the API exists).
- `docker compose ... logs -f postgres` → confirm pgvector extension is available.
- If a provider is unset, that is fine — the platform runs in local/degraded mode by design.

## Troubleshooting
See [DEBUGGING.md](DEBUGGING.md). First checks: the `trace_id` in logs, provider health at
`/ready`, and the job `progress_stage` for stuck uploads.
