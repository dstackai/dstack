from typing import List

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    def __repr__(self) -> str:
        src = self.__class__.__name__
        attr = [f"{key}={val}" for (key, val) in self.__dict__.items() if not key.startswith("_")]
        attr_string = ", ".join(attr)
        return f"{src}({attr_string})"


association_table_user_project = Table(
    "user_project",
    Base.metadata,
    Column("users_name", ForeignKey("users.name")),
    Column("project_name", ForeignKey("projects.name")),
)


class User(Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    token: Mapped[str] = mapped_column(String(200))
    global_role: Mapped[str] = mapped_column(String(100))


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(ForeignKey("projects.name"))
    project: Mapped["Project"] = relationship()

    user_name: Mapped[str] = mapped_column(ForeignKey("users.name"))
    user: Mapped[User] = relationship()

    project_role: Mapped[str] = mapped_column(String(100))


class Project(Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    backend: Mapped[str] = mapped_column(String(30))
    config: Mapped[str] = mapped_column(String(300))
    auth: Mapped[str] = mapped_column(String(300))
    members: Mapped[List[Member]] = relationship(back_populates="project", lazy="selectin")

    def __hash__(self):
        return hash(self.name)
