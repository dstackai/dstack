from contextlib import asynccontextmanager

from alembic import command, config
from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from dstack._internal.server import settings
from dstack._internal.server.services.locking import advisory_lock_ctx
from dstack._internal.server.settings import DATABASE_URL


class Database:
    def __init__(self, url: str):
        self.url = url
        self.engine = create_async_engine(self.url, echo=settings.SQL_ECHO_ENABLED)
        self.session_maker = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        if self.dialect_name == "sqlite":

            @event.listens_for(self.engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection: DBAPIConnection, _: ConnectionPoolEntry):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.execute("PRAGMA busy_timeout=10000;")
                cursor.close()

    @property
    def dialect_name(self) -> str:
        return self.engine.dialect.name

    def get_session(self) -> AsyncSession:
        return self.session_maker()


_db = Database(url=DATABASE_URL)


def get_db() -> Database:
    return _db


def override_db(new_db: Database):
    global _db
    _db = new_db


async def migrate():
    async with _db.engine.connect() as connection:
        async with advisory_lock_ctx(
            bind=connection,
            dialect_name=_db.dialect_name,
            resource="migrations",
        ):
            await connection.run_sync(_run_alembic_upgrade)


async def get_session():
    async with _db.get_session() as session:
        yield session
        await session.commit()


get_session_ctx = asynccontextmanager(get_session)


def session_decorator(func):
    async def new_func(*args, **kwargs):
        async with get_session_ctx() as s:
            return await func(*args, session=s, **kwargs)

    return new_func


def _run_alembic_upgrade(connection):
    alembic_cfg = config.Config()
    alembic_cfg.set_main_option("script_location", settings.ALEMBIC_MIGRATIONS_LOCATION)
    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")
