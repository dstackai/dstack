import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


data_path = os.getenv("DSTACK_HUB_DATA") or Path.home() / ".dstack" / "hub" / "data"
if not data_path.exists():
    data_path.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{str(data_path.absolute())}/sqlite.db", echo=True)
