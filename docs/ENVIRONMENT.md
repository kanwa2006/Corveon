# Corveon — Environment Variables

Authoritative description of every variable. The template is [`../.env.example`](../.env.example);
copy it to `.env` and fill in. Config is loaded via typed `pydantic-settings` (12-factor). Secrets
come from the environment only — never code, never the database.

> **Provider keys are all optional (§23.1).** Leaving a provider blank disables it silently — no
> warning, no retry, no health noise. Zero providers configured is a valid state: Corveon falls
> back to local Ollama, or to degraded (non-LLM) mode.

## Core / runtime
| Var | Default | Meaning |
|---|---|---|
| `CORVEON_ENV` | `development` | `development \| test \| staging \| production` |
| `LOG_LEVEL` | `INFO` | `DEBUG \| INFO \| WARNING \| ERROR` |
| `LOG_FORMAT` | `json` | `json` (prod) or `console` (local) |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Uvicorn bind |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | CORS allow-origin |

## Security / auth
| Var | Default | Meaning |
|---|---|---|
| `JWT_SECRET_KEY` | — | ≥32 random bytes (`openssl rand -hex 32`). **Required.** |
| `JWT_ACCESS_TTL_SECONDS` | `900` | access token lifetime |
| `JWT_REFRESH_TTL_SECONDS` | `1209600` | refresh token lifetime |
| `ARGON2_TIME_COST` / `ARGON2_MEMORY_COST` / `ARGON2_PARALLELISM` | `3` / `65536` / `4` | Argon2id params |

## Database (Postgres 16 + pgvector)
| Var | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…` | async DSN |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | `10` / `5` | connection pool |
| `DB_ENABLE_RLS` | `true` | enable Row-Level Security on `chat_id`/`user_id` |

## Redis (cache + ARQ)
| Var | Default | Meaning |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | cache + queue |
| `EXTERNAL_CACHE_DEFAULT_TTL_SECONDS` | `86400` | default external-API cache TTL |

## Object storage (Cloudflare R2)
| Var | Meaning |
|---|---|
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | credentials |
| `R2_BUCKET` / `R2_ENDPOINT` | bucket + S3-compatible endpoint |
| `R2_SIGNED_URL_TTL_SECONDS` | short-lived signed link TTL (default `300`) |
| `LOCAL_STORAGE_DIR` | default `.data/documents`; dev/test fallback when R2 is unconfigured (ADR-0014); gitignored |

## Embeddings
| Var | Default | Meaning |
|---|---|---|
| `EMBEDDING_MODEL_ID` | `BAAI/bge-small-en-v1.5` | **must produce 384-dim** to match `vector(384)` |
| `EMBEDDING_DEVICE` | `cpu` | inference device |

## AI providers (all optional)
| Var | Meaning |
|---|---|
| `GEMINI_API_KEYS` / `GEMINI_DEFAULT_MODEL` | comma-separated key pool; default model |
| `GEMINI_RPM_LIMIT` | token-bucket cap shared across requests, default `10`; blank = unlimited |
| `ANTHROPIC_API_KEYS` / `ANTHROPIC_DEFAULT_MODEL` / `ANTHROPIC_RPM_LIMIT` | optional high-quality reasoning |
| `OPENAI_API_KEYS` / `OPENAI_DEFAULT_MODEL` / `OPENAI_RPM_LIMIT` | optional |
| `OPENROUTER_API_KEYS` / `OPENROUTER_DEFAULT_MODEL` / `OPENROUTER_RPM_LIMIT` | fallback + model breadth; default RPM `20` (free-tier ceiling) |
| `OLLAMA_BASE_URL` / `OLLAMA_DEFAULT_MODEL` / `OLLAMA_RPM_LIMIT` | implicit local default when reachable; unlimited by default |
| `PROVIDER_PRIORITY` | ordered provider names, highest first |
| `SENSITIVE_TEXT_PROVIDER` | provider for org-trusted/sensitive text (default `ollama`) |
| `LLM_CALLS_PER_REQUEST_BUDGET` | per-request fan-out cap (§23.2) |
| `PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | consecutive failures before a provider's circuit opens (default `3`) |
| `PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | how long a circuit stays open before a half-open probe (default `30`) |

## External medical APIs
Evidence Verification Engine connectors (`app/evidence/connectors/`, blueprint §8). Every
connector's rate limit is a per-process token bucket — a exhausted bucket makes that one source
return no results for the current request rather than blocking or erroring (§8: "conflicting/
insufficient evidence" is itself a provenance class). Responses are cached in Redis, not a Postgres
table (ADR-0017); `EVIDENCE_CACHE_TTL_SECONDS` controls how long.

| Var | Meaning |
|---|---|
| `OPENFDA_API_KEY` / `OPENFDA_BASE_URL` / `OPENFDA_MAX_RPM` | key optional; raises the *daily* cap (openFDA enforces that itself, not this app) — the 240/min rate applies with or without a key |
| `NCBI_EUTILS_API_KEY` / `NCBI_EUTILS_EMAIL` / `NCBI_EUTILS_BASE_URL` / `NCBI_EUTILS_MAX_RPS` | PubMed/PMC E-utilities; email required by NCBI; 10 rps with a key, 3 without (default here assumes a key is configured) |
| `DAILYMED_BASE_URL` / `DAILYMED_MAX_RPS` | structured product labels (SPL); no documented rate limit, default is a conservative choice |
| `CLINICALTRIALS_BASE_URL` / `CLINICALTRIALS_MAX_RPS` | trial evidence; no documented rate limit, default is a conservative choice |
| `MESH_BASE_URL` / `MESH_MAX_RPS` | concept normalization; no documented rate limit, default is a conservative choice |
| `RXNAV_BASE_URL` / `RXNAV_MAX_RPS` | RxNorm normalization (≤20 rps). **No DDI API** (ADR-0004) |
| `EVIDENCE_CACHE_TTL_SECONDS` | how long a connector's response is cached in Redis before re-fetching |

## Observability
| Var | Meaning |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_SERVICE_NAME` | OpenTelemetry export |
| `PROMETHEUS_METRICS_ENABLED` | expose `/metrics` |
| `SENTRY_DSN` | optional; blank disables Sentry |

## Frontend (`NEXT_PUBLIC_*` are browser-exposed)
| Var | Meaning |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | REST base, e.g. `http://localhost:8000/api/v1` |
| `NEXT_PUBLIC_SSE_BASE_URL` | SSE base — points at the **backend**, not Vercel (§23.3) |

## Secrets in each environment
- **Local:** `.env` (gitignored).
- **CI:** GitHub Actions encrypted secrets.
- **Production:** the platform secret manager (Fly/Render). Never commit real values.
