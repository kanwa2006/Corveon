# ADR-0023: Optional Postgres read-replica routing

- **Status:** Accepted
- **Date:** 2026-07-11

## Context
"Enterprise path" (blueprint, `docs/ROADMAP.md`) lists read replicas alongside SSO and
on-prem/Ollama hardening as future work. These three are architecturally independent — this ADR
covers read replicas only. Managed Postgres providers already in Corveon's deployment topology
(Supabase/Neon, `docs/ARCHITECTURE.md` §9) offer read replicas natively; an enterprise deployment
past a single primary's read capacity should be able to point read-only traffic at one without any
business-logic change, the same "absence is normal, presence is opt-in" posture every other
optional subsystem in this codebase already follows (AI providers, R2, Qdrant — ADR-0006,
ADR-0014, ADR-0022).

## Decision
Add one setting, `DATABASE_READ_REPLICA_URL: str | None = None`. `Database`
(`app/data/base.py`) builds a second engine + sessionmaker only when it is set, and exposes
`replica_session()` alongside the existing `session()` — falling back to the primary sessionmaker
when no replica is configured, so every caller of `replica_session()` gets a working session either
way without an `if` of its own. `app/api/deps.py` gains `ReadOnlyDbDep`/`ReadOnlyRlsDbDep`
mirroring `DbDep`/`RlsDbDep` exactly, including a fresh `set_rls_user` call on the replica session:
the RLS GUC (`app.current_user_id`) is transaction-local *session* state (ADR-0013), never
replicated between physical connections, so a replica session needs the identical per-request RLS
setup a primary session gets — this is not optional even for reads.

`POST /chats/{id}/search` (the one existing endpoint that is purely a read — no write anywhere in
its call path) switches from `RlsDbDep` to `ReadOnlyRlsDbDep`. `GET /ready` additionally pings the
replica when configured, so an operator who wired one up gets it covered by readiness like every
other dependency.

## Consequences
- Zero behavior change when `DATABASE_READ_REPLICA_URL` is unset — `replica_session()` degrades to
  exactly `session()`, so every existing endpoint, test, and deployment continues to hit only the
  primary, unchanged.
- Every write path is untouched — nothing here changes what any endpoint writes to, only which
  connection a handful of pure-read endpoints read from.
- `Database.dispose()` now disposes both engines when a replica is configured — no leaked pool on
  shutdown.
- Read-after-write consistency is the deployment operator's problem, not this code's: a request
  that writes then immediately reads back its own write (none currently do, since `search_chat`
  never writes) could observe replication lag if routed to a replica. Nothing in this change routes
  a write-adjacent read to the replica — only the one endpoint that never writes.
- Only one endpoint (`search_chat`) is wired to the replica in this change, deliberately — it is the
  only genuinely read-only endpoint that exists today; wiring others (e.g. a future analytics
  endpoint) is additive, not a redesign, since `ReadOnlyRlsDbDep` already exists for them to adopt.

## Alternatives considered
- **A new standalone `ReplicaDatabase` class:** rejected — `Database` already owns exactly the
  engine+sessionmaker pairing a replica needs; a second class would duplicate `dispose()`/`ping()`
  logic and require every one of `Database`'s 5 construction sites (`app/main.py`,
  `app/workers/main.py`, and 3 CLI loader scripts) to also know about the new class for no benefit.
- **Route all reads through the replica automatically (e.g. a query-type-sniffing session):**
  rejected — implicit, hard to audit, and risks silently routing a read that actually needs
  read-your-writes consistency onto a lagging replica. Explicit per-endpoint opt-in
  (`ReadOnlyRlsDbDep` instead of `RlsDbDep`) keeps the choice visible in the router signature.
