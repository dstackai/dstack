from sqlalchemy import Column, String

from dstack.hub.db import Database


class Base:
    def __repr__(self) -> str:
        src = self.__class__.__name__
        attr = [f"{key}= {val}" for (key, val) in self.__dict__.items() if not key.startwith("_")]
        attr_string = ",".join(attr)
        return f"{src}({attr_string})"


class User(Base, Database.Base):
    __tablename__ = "users"

    name = Column(String(30), primary_key=True)
    token = Column(String(200))

    def __init__(self, name: str, token: str):
        self.name = name
        self.token = token

    def __repr__(self) -> str:
        return super().__repr__()


class Hub(Base, Database.Base):
    __tablename__ = "hubs"

    name = Column(String(30), primary_key=True)
    backend = Column(String(30))
    config = Column(String(300))

    def __init__(self, name: str, backend: str, config: str):
        self.name = name
        self.backend = backend
        self.config = config

    def __repr__(self) -> str:
        return super().__repr__()
