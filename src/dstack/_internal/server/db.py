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

    def get_session(self) -> AsyncSession:
        return self.session_maker()


db = Database(url=DATABASE_URL)


def override_db(new_db: Database):
    global db
    db = new_db


@event.listens_for(db.engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection: DBAPIConnection, _: ConnectionPoolEntry):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


async def migrate():
    async with db.engine.begin() as connection:
        await connection.run_sync(_run_alembic_upgrade)


async def get_session():
    async with db.get_session() as session:
        async with session as s:
            yield s
            await s.commit()


def reuse_or_make_session(func):
    async def new_func(*args, session: Optional[AsyncSession] = None, **kwargs):
        session_ = session
        if session_ is None:
            session_ = db.get_session()
        res = await func(*args, session=session_, **kwargs)
        if session is None:
            await session_.close()
        return res

    return new_func


def _run_alembic_upgrade(connection):
    alembic_cfg = config.Config()
    alembic_cfg.set_main_option("script_location", "dstack._internal.server:migrations")
    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")
