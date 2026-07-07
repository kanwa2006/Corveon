# ADR-0013: The app's Postgres role must be a genuine non-superuser for RLS to apply

- **Status:** Accepted
- **Date:** 2026-07-08

## Context
Building the first table with Row-Level Security (`chats`, migration 0002 — the mechanism
docs/ARCHITECTURE.md §5 and CLAUDE.md's "per-chat isolation is absolute" golden rule require),
a genuine cross-user RLS-bypass test proved the policy had **no effect at all**: a second user
could read the first user's row despite `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL
SECURITY` both being set.

Root cause: the official `postgres`/`pgvector` Docker image grants unconditional `SUPERUSER` to
whatever role `POSTGRES_USER` bootstraps as. **Postgres superusers bypass RLS unconditionally,
regardless of `FORCE`** — this is documented Postgres behavior, not a bug. Our `docker-compose.yml`
and CI's Postgres service both set `POSTGRES_USER: corveon`, so the app's own `corveon` role was
silently a superuser the entire time, and every RLS policy we might have written would have been
a no-op. Attempting to fix this by demoting the role in place (`ALTER ROLE corveon NOSUPERUSER`)
fails outright — Postgres specifically protects the bootstrap role from being demoted.

## Decision
Bootstrap Postgres containers (local `docker-compose.yml` and CI) using the **default** `postgres`
superuser (`POSTGRES_USER`/`POSTGRES_DB` left unset), then create `corveon` as a **separate,
ordinary, database-owning role** via an init step:
```sql
CREATE ROLE corveon WITH LOGIN PASSWORD 'corveon';
CREATE DATABASE corveon OWNER corveon;
```
- **Local:** `infra/postgres-init/01-create-corveon-role.sql`, mounted at
  `/docker-entrypoint-initdb.d/` (runs automatically on first container start).
- **CI:** an explicit workflow step runs the same SQL against the service container before
  migrations/tests run (GitHub Actions service containers don't support custom init-script
  mounting).

Because `corveon` **owns** the tables it creates via Alembic (and is not superuser), a single
`FORCE ROW LEVEL SECURITY` per table is sufficient to make RLS apply to the app's own queries —
no second "restricted app role" or split migrations/app connection string is needed. The `DATABASE_URL`
value (`postgresql+asyncpg://corveon:corveon@localhost:5432/corveon`) is unchanged from the
developer's perspective.

Policies additionally guard against a related edge case: Postgres resets an unset custom GUC to
`''` (empty string, not `NULL`) once its `LOCAL` scope ends on a pooled connection. A bare
`current_setting('app.current_user_id', true)::uuid` cast throws a raw error in that state instead
of gracefully denying. Policies wrap it in `nullif(..., '')` so an application bug that forgets to
call `set_config()` fails closed (silently, as "no rows") rather than surfacing a raw Postgres
exception.

## Consequences
- RLS now genuinely enforces per-owner isolation — verified with a dedicated test that proves a
  second user cannot read, and cannot `INSERT` rows for, another user's data at the raw-SQL level
  (independent of any application-code bug).
- Every future content table with an RLS policy inherits this same pattern for free: one role,
  `ENABLE` + `FORCE ROW LEVEL SECURITY`, a `USING`/`WITH CHECK` policy referencing
  `nullif(current_setting('app.current_user_id', true), '')::uuid`.
- Local first-time setup requires a fresh volume for the init script to run (`docker compose down
  -v` before `up` if upgrading an existing local Postgres data directory created before this ADR).
- CI gained one explicit step (create the role) before migrations; a minor, one-time addition, not
  a workflow redesign.

## Alternatives considered
- **A second, restricted `corveon_app` role for runtime queries, keeping `corveon` (superuser) for
  migrations only:** works, but needs two connection strings (`DATABASE_URL` vs a migrations-only
  URL) and default-privilege GRANTs kept in sync as new tables are added. More moving parts for no
  extra security benefit once the single-non-superuser-owner approach was proven to work.
- **`ALTER ROLE corveon NOSUPERUSER` on the existing bootstrap role:** rejected by Postgres outright
  ("the bootstrap user must have the SUPERUSER attribute") — not viable.
