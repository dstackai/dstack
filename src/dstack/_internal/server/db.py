import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from alembic import command, config
from sqlalchemy import AsyncAdaptedQueuePool, event, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry

from dstack._internal.server import settings
from dstack._internal.server.services.locking import try_advisory_lock_ctx


class Database:
    def __init__(self, url: str, engine: Optional[AsyncEngine] = None):
        self.url = url
        if engine is not None:
            self.engine = engine
        else:
            self.engine = create_async_engine(
                self.url,
                echo=settings.SQL_ECHO_ENABLED,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                connect_args=self._get_connect_args(self.url),
            )
        self.session_maker = async_sessionmaker(
            bind=self.engine,  # type: ignore[assignment]
            expire_on_commit=False,
            # Disable autoflush to avoid accidental long write transactions on SQLite.
            autoflush=False,
            class_=AsyncSession,
        )

        if self.dialect_name == "sqlite":

            @event.listens_for(self.engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection: DBAPIConnection, _: ConnectionPoolEntry):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA busy_timeout=30000;")
                cursor.close()

    @property
    def dialect_name(self) -> str:
        return self.engine.dialect.name

    def get_session(self, bind: Optional[AsyncConnection] = None) -> AsyncSession:
        """
        Returns a new session. If `bind` is given, the session runs on that connection
        instead of checking connections out of the pool. The connection must not be in
        a transaction, otherwise the session joins it and its commits do not commit.
        """
        if bind is None:
            return self.session_maker()
        return self.session_maker(bind=bind)

    def _get_connect_args(self, url: str) -> dict:
        if make_url(url).get_backend_name() == "postgresql":
            # TODO: Consider setting "command_timeout" high for migrations
            # and low for queries – requires a separate Database instance for migrations.
            return {"command_timeout": settings.DB_COMMAND_TIMEOUT}
        return {}


def get_new_db() -> Database:
    """
    Creates a new Database with a new Engine.
    Use this when you need to access the DB in a new thread instead of calling Database directly
    since it's easier to monkey-patch.
    """
    return Database(url=settings.get_database_url())


_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = get_new_db()
    return _db


def override_db(new_db: Database):
    global _db
    _db = new_db


_MIGRATIONS_LOCK_POLL_INTERVAL = 1
_MIGRATIONS_LOCK_MAX_ATTEMPTS = 600


async def migrate():
    db = get_db()
    # The lock is polled instead of awaited in pg_advisory_lock() to avoid this:
    # migrations waiting for older snapshots to finish (e.g. CREATE INDEX CONCURRENTLY)
    # wait for the blocked replicas waiting for the "migrations" lock, deadlocking both.
    async with db.engine.connect() as connection:
        for _ in range(_MIGRATIONS_LOCK_MAX_ATTEMPTS):
            async with try_advisory_lock_ctx(
                bind=connection,
                dialect_name=db.dialect_name,
                resource="migrations",
            ) as locked:
                # End the attempt's transaction so that no snapshot is held while waiting.
                await connection.commit()
                if locked:
                    await connection.run_sync(_run_alembic_upgrade)
                    return
            await asyncio.sleep(_MIGRATIONS_LOCK_POLL_INTERVAL)
    raise TimeoutError(
        "Timed out waiting for the migrations lock."
        " Another server replica may be running long migrations, or a replica that lost"
        " connectivity may still hold it: check pg_locks for the advisory lock"
        " and terminate the holder's backend if it is gone."
    )


async def get_session():
    async with get_db().get_session() as session:
        yield session
        await session.commit()


get_session_ctx = asynccontextmanager(get_session)


def session_decorator(func):
    async def new_func(*args, **kwargs):
        async with get_session_ctx() as s:
            return await func(*args, session=s, **kwargs)

    return new_func


def is_db_sqlite() -> bool:
    return get_db().dialect_name == "sqlite"


def is_db_postgres() -> bool:
    return get_db().dialect_name == "postgresql"


async def sqlite_commit(session: AsyncSession):
    """
    Commit an sqlite transaction.
    Should be used before taking locks in active sessions to see committed changes.
    """
    if is_db_sqlite():
        await session.commit()


def _run_alembic_upgrade(connection):
    alembic_cfg = config.Config()
    alembic_cfg.set_main_option("script_location", settings.ALEMBIC_MIGRATIONS_LOCATION)
    alembic_cfg.set_main_option("recursive_version_locations", "true")
    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")
