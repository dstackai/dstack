import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

data_path = os.getenv("DSTACK_HUB_DATA") or Path.home() / ".dstack" / "hub" / "data"
if not data_path.exists():
    data_path.mkdir(parents=True, exist_ok=True)


class Database:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{str(data_path.absolute())}/sqlite.db", echo=False
    )
    Base = declarative_base()
    Session = sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(Database.engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection: DBAPIConnection, _: ConnectionPoolEntry):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
