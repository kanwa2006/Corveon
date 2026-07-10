# ADR-0017: External evidence cache lives in Redis, not a Postgres `external_cache` table

- **Status:** Accepted
- **Date:** 2026-07-10

## Context
The blueprint names the external-API cache in two places with two different mechanisms: §10.1's
schema list includes `external_cache(key, source, payload JSONB, fetched_at, ttl)` as a Postgres
table, while §10.4 says plainly "Redis caches external-API responses keyed by
`{source}:{query_hash}` with source-appropriate TTLs." Building both would mean two caches for the
same data, with no defined precedence between them — genuine redundancy, not defense in depth.

Redis is already wired into this process (ARQ queue, refresh-token denylist, rate-limit state,
ADR-0011) and gives TTL expiry for free via `SETEX`/`EXPIRE` — no cleanup job, no migration, no
extra table to keep in sync with a `fetched_at`/`ttl` pair that Postgres has no native way to expire
on its own.

## Decision
External evidence-connector responses (PubMed, DailyMed, openFDA, ClinicalTrials.gov, MeSH, RxNorm)
are cached in Redis only, keyed `evidence:{source}:{sha256(query)}`, with a per-source TTL. No
`external_cache` Postgres table is created.

## Consequences
- One cache mechanism, one place to look when debugging a stale or missing result.
- Cache entries do not survive a Redis flush/restart — acceptable, since every connector can always
  re-fetch from the source API; this is a performance cache, not a system of record.
- If a future requirement needs the cache to be queryable/joinable in SQL (e.g. for an admin view
  of what's cached), a Postgres table can be added later without touching connector code — they
  depend on a small cache interface, not directly on Redis.

## Alternatives considered
- **Postgres `external_cache` table** (as §10.1 lists): rejected — redundant with Redis, and
  Postgres has no built-in TTL expiry, so it would need its own periodic cleanup job for a table
  that exists purely to avoid re-fetching data already fetchable from the source of truth.
- **Both, Postgres as source of truth + Redis as read-through cache**: rejected as unnecessary
  complexity for a cache with no durability requirement — nothing in the Evidence Verification
  Engine needs cached API responses to survive past their TTL.
