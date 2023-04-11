import os
from pathlib import Path
from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

data_path = os.getenv("DSTACK_HUB_DATA") or Path.home() / ".dstack" / "hub" / "data"
if not data_path.exists():
    data_path.mkdir(parents=True, exist_ok=True)


class Database:
    def __init__(self, url: Optional[str] = None):
        if url is None:
            url = f"sqlite+aiosqlite:///{str(data_path.absolute())}/sqlite.db"
        self.url = url
        self.engine = create_async_engine(self.url, echo=False)
        self.session_maker = sessionmaker(
            bind=self.engine, expire_on_commit=False, class_=AsyncSession
        )

    def get_session(self) -> AsyncSession:
        return self.session_maker()


db = Database()


def override_db(new_db: Database):
    global db
    db = new_db


@event.listens_for(db.engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection: DBAPIConnection, _: ConnectionPoolEntry):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


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
