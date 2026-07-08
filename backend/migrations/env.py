"""Alembic environment — async engine, sourcing the DSN from Settings
(single source of truth, docs/ENVIRONMENT.md) rather than alembic.ini."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

import app.data.models  # noqa: F401  registers all models on Base.metadata
from alembic import context
from app.core.config import get_settings
from app.data.base import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Indexes created via raw DDL rather than a tracked model Index (ADR-0015)
# are, by definition, absent from target_metadata — without this filter,
# autogenerate would see them as "extra" objects in the live database and
# propose dropping them on every single run. include_object tells it to
# simply not compare these objects in either direction.
_AUTOGENERATE_IGNORED_OBJECT_NAMES = {"ix_chunk_embeddings_embedding_hnsw"}


def include_object(
    object: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    del object, reflected, compare_to  # part of Alembic's required hook signature
    return not (type_ == "index" and name in _AUTOGENERATE_IGNORED_OBJECT_NAMES)


def get_url() -> str:
    return get_settings().DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
