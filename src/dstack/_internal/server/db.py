from contextlib import asynccontextmanager
from typing import Optional

from alembic import command, config
from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from dstack._internal.server.settings import DATABASE_URL


class Database:
    def __init__(self, url: str):
        self.url = url
        self.engine = create_async_engine(self.url, echo=False)
        self.session_maker = sessionmaker(
            bind=self.engine, expire_on_commit=False, class_=AsyncSession
        )

        @event.listens_for(self.engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection: DBAPIConnection, _: ConnectionPoolEntry):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    def get_session(self) -> AsyncSession:
        return self.session_maker()


db = Database(url=DATABASE_URL)


def override_db(new_db: Database):
    global db
    db = new_db


async def migrate():
    async with db.engine.begin() as connection:
        await connection.run_sync(_run_alembic_upgrade)


async def get_session():
    async with db.get_session() as session:
        async with session as s:
            yield s
            await s.commit()


get_session_ctx = asynccontextmanager(get_session)


def session_decorator(func):
    async def new_func(*args, **kwargs):
        async with get_session_ctx() as s:
            return await func(*args, session=s, **kwargs)

    return new_func


def _run_alembic_upgrade(connection):
    alembic_cfg = config.Config()
    alembic_cfg.set_main_option("script_location", "dstack._internal.server:migrations")
    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")
