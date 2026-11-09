"""Alembic environment.

Two deliberate choices:

* ``target_metadata`` is ``Base.metadata`` after importing every model module, so
  autogenerate sees the full schema and a table can never be silently missed.
* autogenerate compares types and server defaults, because this schema relies on
  ``server_default`` for counters and JSONB defaults; missing them in a migration
  would make a fresh database differ from an upgraded one.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.core.config import Settings
from app.db.base import Base
from app.models import (  # noqa: F401 - imported for their side effect on metadata
    CropProfile,
    Device,
    Disease,
    DiseaseEpisode,
    Farm,
    ForumComment,
    ForumPost,
    ForumReport,
    HarvestRecord,
    Plant,
    Region,
    Reminder,
    Scan,
    ScanFeedback,
    User,
    WeatherSnapshot,
)
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Alembic runs synchronously, so the async driver is rewritten to psycopg."""
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    return Settings().sync_database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # A migration that renames a column must fail loudly rather than drop
            # and recreate it; the naming convention makes this rare anyway.
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
