"""Typed application configuration (12-factor, pydantic-settings).

Transcribes the environment contract documented in docs/ENVIRONMENT.md into a
single typed ``Settings`` object. Every field here corresponds to a variable in
.env.example; this module is the only place that reads ``os.environ`` directly.

All AI provider fields are optional — an absent provider is a normal, valid
state (ADR-0006, CLAUDE.md §12): this module never raises or warns because a
provider key is unset. Only genuinely required infrastructure (``JWT_SECRET_KEY``,
``DATABASE_URL``) is mandatory.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Core / runtime ───────────────────────────────────────
    CORVEON_ENV: Literal["development", "test", "staging", "production"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"
    API_HOST: str = "0.0.0.0"  # noqa: S104  # nosec B104 -- intentional container-friendly bind-all
    API_PORT: int = 8000
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # ── Security / auth ──────────────────────────────────────
    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_ACCESS_TTL_SECONDS: int = 900
    JWT_REFRESH_TTL_SECONDS: int = 1_209_600
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536
    ARGON2_PARALLELISM: int = 4

    # ── Database (Postgres 16 + pgvector) ────────────────────
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 5
    DB_ENABLE_RLS: bool = True
    # Optional read-replica for pure-read endpoints (ADR-0023). Unset is a
    # normal, valid state — every read falls back to the primary, same
    # posture as every other optional subsystem (§23.1).
    DATABASE_READ_REPLICA_URL: str | None = None

    # ── Redis (cache + ARQ) ───────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    EXTERNAL_CACHE_DEFAULT_TTL_SECONDS: int = 86400

    # ── Object storage (Cloudflare R2) ───────────────────────
    R2_ACCOUNT_ID: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_BUCKET: str = "corveon-documents"
    R2_ENDPOINT: str | None = None
    R2_SIGNED_URL_TTL_SECONDS: int = 300
    # Dev/test fallback when R2 is not configured (ADR-0014); gitignored.
    LOCAL_STORAGE_DIR: str = ".data/documents"

    # ── Embeddings ────────────────────────────────────────────
    EMBEDDING_MODEL_ID: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DEVICE: str = "cpu"

    # ── Vector store (ADR-0001, ADR-0022) ────────────────────
    # pgvector (inside Postgres) is the default; Qdrant is an opt-in
    # alternative for deployments past pgvector's comfort zone or already
    # running a Qdrant cluster. Business logic never sees this choice — it
    # only ever talks to app.data.vectorstore.base.VectorStore.
    VECTOR_STORE: Literal["pgvector", "qdrant"] = "pgvector"
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    # ── AI providers — all optional (§23.1, ADR-0006) ────────
    GEMINI_API_KEYS: str | None = None
    GEMINI_DEFAULT_MODEL: str = "gemini-2.5-flash-lite"
    # Conservative default matching the documented Gemini free-tier Flash
    # RPM (blueprint §5) — override per your actual model/plan. None = no
    # token-bucket rate limiting applied to this provider.
    GEMINI_RPM_LIMIT: int | None = 10
    ANTHROPIC_API_KEYS: str | None = None
    ANTHROPIC_DEFAULT_MODEL: str = "claude-sonnet-5"
    ANTHROPIC_RPM_LIMIT: int | None = None
    OPENAI_API_KEYS: str | None = None
    OPENAI_DEFAULT_MODEL: str = "gpt-4.1-mini"
    OPENAI_RPM_LIMIT: int | None = None
    OPENROUTER_API_KEYS: str | None = None
    OPENROUTER_DEFAULT_MODEL: str | None = None
    # OpenRouter's free-tier cap never rises with credits (blueprint §5).
    OPENROUTER_RPM_LIMIT: int | None = 20
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_DEFAULT_MODEL: str = "llama3.1"
    # Local inference has no vendor rate limit by default.
    OLLAMA_RPM_LIMIT: int | None = None
    PROVIDER_PRIORITY: str = "gemini,openrouter,ollama"
    SENSITIVE_TEXT_PROVIDER: str = "ollama"
    LLM_CALLS_PER_REQUEST_BUDGET: int = 8
    # Consecutive provider failures before its circuit breaker opens, and how
    # long it then stays open before allowing a half-open probe (§23.1).
    PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS: float = 30.0

    # ── External medical APIs ────────────────────────────────
    OPENFDA_API_KEY: str | None = None
    OPENFDA_BASE_URL: str = "https://api.fda.gov"
    # openFDA: 240 req/min both with and without a key; a key raises the
    # daily cap (1,000/day -> 120,000/day), which this per-process RPM
    # limiter doesn't model — daily caps are enforced by openFDA itself.
    OPENFDA_MAX_RPM: int = 240
    NCBI_EUTILS_API_KEY: str | None = None
    NCBI_EUTILS_EMAIL: str | None = None
    NCBI_EUTILS_BASE_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    # PubMed/PMC E-utilities: 3 req/s without a key, 10 req/s with one (§8).
    NCBI_EUTILS_MAX_RPS: int = 10
    DAILYMED_BASE_URL: str = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
    # DailyMed publishes no documented rate limit; a conservative default
    # keeps this a good API citizen without a blueprint-specified number to
    # match.
    DAILYMED_MAX_RPS: int = 5
    CLINICALTRIALS_BASE_URL: str = "https://clinicaltrials.gov/api/v2"
    CLINICALTRIALS_MAX_RPS: int = 5
    MESH_BASE_URL: str = "https://id.nlm.nih.gov/mesh"
    MESH_MAX_RPS: int = 5
    RXNAV_BASE_URL: str = "https://rxnav.nlm.nih.gov/REST"
    RXNAV_MAX_RPS: int = 20
    EVIDENCE_CACHE_TTL_SECONDS: int = 86400

    # ── Medication-Safety Engine (data/loaders/README.md) ───────
    # Pinned, checksummed local snapshots, never fetched at request time
    # (ADR-0004, ADR-0019). Blank *_SNAPSHOT_PATH means "no snapshot
    # imported yet" for that source (DDI detection then relies solely on
    # the openFDA label-derived fallback; PIP screening simply has no
    # criteria to check) — absence is normal, same posture as an
    # unconfigured AI provider (§23.1). ``app/medication/snapshot_sync.py``
    # reads these to reproducibly (re)import each configured source; a
    # path set without its paired version is a configuration error, since
    # an automated import needs an explicit, reviewed version label, never
    # one inferred from file content or mtime.
    DDINTER_SNAPSHOT_PATH: str | None = None
    DDINTER_SNAPSHOT_VERSION: str | None = None
    BEERS_2023_SNAPSHOT_PATH: str | None = None
    BEERS_2023_SNAPSHOT_VERSION: str | None = None
    STOPP_START_V3_SNAPSHOT_PATH: str | None = None
    STOPP_START_V3_SNAPSHOT_VERSION: str | None = None

    # ── Observability ─────────────────────────────────────────
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = "corveon-api"
    PROMETHEUS_METRICS_ENABLED: bool = True
    SENTRY_DSN: str | None = None

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _reject_placeholder_secret(cls, value: str) -> str:
        if value.strip().lower().startswith("change-me"):
            raise ValueError(
                "JWT_SECRET_KEY is still the .env.example placeholder — "
                "generate a real value with `openssl rand -hex 32`."
            )
        return value

    @model_validator(mode="after")
    def _qdrant_url_required_when_selected(self) -> Settings:
        if self.VECTOR_STORE == "qdrant" and not self.QDRANT_URL:
            raise ValueError("QDRANT_URL is required when VECTOR_STORE=qdrant.")
        return self

    def _csv(self, raw: str | None) -> list[str]:
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def gemini_api_key_pool(self) -> list[str]:
        return self._csv(self.GEMINI_API_KEYS)

    @property
    def anthropic_api_key_pool(self) -> list[str]:
        return self._csv(self.ANTHROPIC_API_KEYS)

    @property
    def openai_api_key_pool(self) -> list[str]:
        return self._csv(self.OPENAI_API_KEYS)

    @property
    def openrouter_api_key_pool(self) -> list[str]:
        return self._csv(self.OPENROUTER_API_KEYS)

    @property
    def provider_priority_list(self) -> list[str]:
        return self._csv(self.PROVIDER_PRIORITY)

    @property
    def is_production(self) -> bool:
        return self.CORVEON_ENV == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings instance (FastAPI dependency-friendly)."""
    return Settings()  # values sourced from env/.env
