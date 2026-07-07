# Alembic migrations (ADR-0002 policy, blueprint §10.3)

- **One migration per schema change.** Small, reviewable, single-purpose.
- **Forward-only in production.** Downgrade paths are written and tested in CI, but production
  never runs a downgrade; roll forward with a new migration instead.
- **No auto-generated migration is merged unreviewed.** `alembic revision --autogenerate` is a
  starting point only — every migration is read and edited by a human before merge.
- **CI asserts models ↔ migrations are in sync** (a fresh `--autogenerate` against `head` must
  produce an empty diff). This directly kills the "migration conflicts" failure category.
- **Every content-bearing table carries `chat_id`**, and migrations that add such tables must
  also add the corresponding Row-Level Security policy (§10.2).

`env.py`, `script.py.mako`, and `alembic.ini` are generated when the data layer lands
(Roadmap Week 1). This directory is committed now so the policy travels with the repo.
