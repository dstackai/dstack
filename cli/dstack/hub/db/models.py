from typing import List

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dstack.hub.db import Database


class Base:
    def __repr__(self) -> str:
        src = self.__class__.__name__
        attr = [f"{key}= {val}" for (key, val) in self.__dict__.items() if not key.startwith("_")]
        attr_string = ",".join(attr)
        return f"{src}({attr_string})"


association_table_user_hub = Table(
    "user_hub",
    Database.Base.metadata,
    Column("users_name", ForeignKey("users.name")),
    Column("hub_name", ForeignKey("hubs.name")),
)


class Role(Base, Database.Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30))

    def __repr__(self) -> str:
        return super().__repr__()


class User(Base, Database.Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    token: Mapped[str] = mapped_column(String(200))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    hub_role: Mapped[Role] = relationship()

    def __repr__(self) -> str:
        return super().__repr__()


class Member(Base, Database.Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hub_name: Mapped[str] = mapped_column(ForeignKey("hubs.name"))

    user_name: Mapped[str] = mapped_column(ForeignKey("users.name"))
    user: Mapped[User] = relationship()

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    hub_role: Mapped[Role] = relationship()

    def __repr__(self) -> str:
        return super().__repr__()


class Hub(Base, Database.Base):
    __tablename__ = "hubs"

    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    backend: Mapped[str] = mapped_column(String(30))
    config: Mapped[str] = mapped_column(String(300))
    auth: Mapped[str] = mapped_column(String(300))
    members: Mapped[List[Member]] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return super().__repr__()


class Scope(Base, Database.Base):
    __tablename__ = "scopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return super().__repr__()
