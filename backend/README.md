# Corveon backend

FastAPI + async SQLAlchemy + ARQ. See [`../CLAUDE.md`](../CLAUDE.md) for the engineering
contract and [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for the design.

## Local dev
```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.12
pip install -e ".[dev]"
ruff check . && mypy app && pytest                  # quality gates
# uvicorn app.main:app --reload                       # once app/main.py exists
```

## Layout (single-responsibility packages — see CLAUDE.md §4)
```
app/api            thin FastAPI routers (contract only)
app/orchestrator   routing policy + typed async state graph
app/agents         one file per single-responsibility agent
app/providers      provider adapters + key-pool / failover (no business logic)
app/evidence       evidence verification engine + trusted-source connectors
app/medication     deterministic rules engine (RxNorm, DDI, renal, PIP)
app/ingestion      parsers, OCR, chunking, embedding
app/data           SQLAlchemy models, repositories, RLS
app/core           config, security, logging, tracing
app/workers        ARQ tasks
migrations         Alembic (forward-only in prod; models↔migrations synced in CI)
tests              mirrors app/ by layer
```

## Non-negotiables
- Every content query is scoped by `chat_id` (per-chat isolation is absolute).
- Business logic never names a concrete AI provider — go through the registry/router.
- Medication rules engine is the source of truth; the LLM only parses and explains.
- Add an OTel span + `trace_id` log to every new code path.
