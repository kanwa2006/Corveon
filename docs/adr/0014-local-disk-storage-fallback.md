# ADR-0014: Local-disk object storage fallback when R2 is unconfigured

- **Status:** Accepted
- **Date:** 2026-07-08

## Context
Uploaded documents are stored as objects (`docs/ARCHITECTURE.md` §1, Data Layer: Cloudflare R2).
`R2_*` env vars are already documented as optional (`docs/ENVIRONMENT.md`) — but unlike an AI
provider, object storage is not optional for the upload feature to function at all: some backing
store must exist for local dev and CI, neither of which has real R2 credentials.

## Decision
Introduce an `ObjectStorage` protocol (`app/core/storage.py`) with two implementations:
- **`R2Storage`** — boto3 S3-compatible client against `R2_ENDPOINT`/`R2_BUCKET`, used whenever
  all four R2 credentials are configured. Sync boto3 calls are wrapped in `asyncio.to_thread` to
  stay async-first.
- **`LocalDiskStorage`** — writes under `LOCAL_STORAGE_DIR` (new env var, default
  `.data/documents`, gitignored), used whenever R2 is not configured.

Selection is automatic and silent — the same "absence ≠ failure" posture ADR-0006 established for
AI providers, applied to storage: an unconfigured optional integration degrades to a working local
default rather than erroring.

## Consequences
- Local dev and CI can exercise the full upload → parse → chunk → embed pipeline with zero cloud
  credentials.
- Production (R2 configured) and local dev exercise the same `ObjectStorage` interface, so the
  ingestion pipeline code is identical in both.
- Tradeoff: `LocalDiskStorage` is single-node — fine for a solo-dev MVP, not for multi-instance
  production. Production deployment requires R2 to be configured (documented in `DEPLOYMENT.md`).

## Alternatives considered
- **Require R2 everywhere, including CI:** forces either real cloud credentials in CI (cost/secret
  management for a solo-dev OSS project) or a mocked S3 server (e.g. moto) — extra test
  infrastructure for no behavioral gain over a real local-disk implementation.
- **In-memory storage for tests only:** would leave local dev (`docker compose up`, no R2 keys)
  unable to actually try the feature — a worse default for the documented free-tier workflow.
