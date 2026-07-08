-- Row-Level Security (docs/ARCHITECTURE.md §5, ADR-0013) requires the
-- application's own DB role to be a genuine non-superuser: Postgres
-- superusers bypass RLS unconditionally, regardless of FORCE ROW LEVEL
-- SECURITY. The official Postgres image's bootstrap POSTGRES_USER is always
-- superuser and Postgres refuses to let that specific "bootstrap" role be
-- demoted (ALTER ROLE ... NOSUPERUSER is rejected on it outright) — so this
-- container bootstraps as the default "postgres" superuser (see
-- docker-compose.yml, which no longer sets POSTGRES_USER/POSTGRES_DB) and
-- creates "corveon" here as a separate, ordinary, database-owning role.
--
-- Because "corveon" OWNS the tables it creates via Alembic migrations, and
-- is NOT a superuser, FORCE ROW LEVEL SECURITY (set per-table in each
-- migration that needs it) correctly applies to its own queries too — no
-- second "restricted app role" or split connection string is needed.

CREATE ROLE corveon WITH LOGIN PASSWORD 'corveon';
CREATE DATABASE corveon OWNER corveon;
