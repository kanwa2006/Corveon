"""Data layer (§10) — SQLAlchemy 2.0 models, repositories, RLS.

PostgreSQL 16 + pgvector (HNSW, ``vector(384)``) is the single source of truth for
tenancy and isolation. Every content-bearing table carries ``chat_id``. The
repository layer refuses any query lacking a ``chat_id`` predicate; Postgres
Row-Level Security policies keyed on ``chat_id``/``user_id`` provide defense in
depth. Similarity queries always filter by ``chat_id`` AND ``model_id``. All IDs
are UUID; all timestamps UTC.
"""
