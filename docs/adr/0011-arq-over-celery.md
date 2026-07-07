# ADR-0011: ARQ over Celery for the async task queue

- **Status:** Accepted
- **Date:** 2026-07-07

## Context
The upload/verify/export pipeline needs a background task system that pairs cleanly with FastAPI's
async event loop, for a solo dev on free infrastructure (single Redis already present for caching).

## Decision
Use **ARQ** (async Redis queue) for all background jobs (ingest, ocr, embed, verify, export, delete).

## Consequences
- Async-native — matches the FastAPI/asyncpg/httpx stack; no thread/event-loop impedance mismatch.
- **Redis-only** — the same Upstash Redis serves cache **and** queue; no separate broker to operate.
- Tiny operational footprint suited to a solo dev.
- Tradeoff: a smaller ecosystem than Celery (fewer plugins, less tooling). Acceptable for our job
  shapes; heartbeats/timeouts/retries are implemented explicitly (§12).

## Alternatives considered
- **Celery:** mature and feature-rich, but sync-first, heavier to operate, and typically wants a
  dedicated broker — more weight than a solo-dev MVP warrants.
- **FastAPI BackgroundTasks:** in-process only; no durability, retries, or worker isolation.
