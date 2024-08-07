import asyncio
from logging.config import fileConfig

import alembic_postgresql_enum  # noqa: F401
from alembic import context
from sqlalchemy import Connection, MetaData, text

from dstack._internal.server.db import db
from dstack._internal.server.models import BaseModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = BaseModel.metadata


def set_target_metadata(metadata: MetaData):
    global target_metadata
    target_metadata = metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode.
    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.
    Calls to context.execute() here emit the given string to the
    script output.
    """
    context.configure(
        url=db.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# Programmatic API use (connection sharing) With Asyncio
# https://alembic.sqlalchemy.org/en/latest/cookbook.html#programmatic-api-use-connection-sharing-with-asyncio
def run_migrations_online():
    """Run migrations in 'online' mode.
    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connection = config.attributes.get("connection", None)
    if connection is None:
        asyncio.run(run_async_migrations())
    else:
        run_migrations(connection)


def run_migrations(connection: Connection):
    # Temporarily disable foreign keys,
    # so that sqlite batch table migrations are performed without data loss:
    # https://alembic.sqlalchemy.org/en/latest/batch.html#dealing-with-referencing-foreign-keys
    if db.get_dialect_name() == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=OFF;"))
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    if db.get_dialect_name() == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=ON;"))
    connection.commit()


async def run_async_migrations():
    engine = db.engine
    async with db.engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


def main():
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()


# invoked via alembic command
if __name__ == "env_py":
    main()
