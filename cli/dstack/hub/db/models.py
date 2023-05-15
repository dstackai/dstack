from typing import List

from sqlalchemy import ForeignKey, Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

constraint_naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=constraint_naming_convention)

    def __repr__(self) -> str:
        src = self.__class__.__name__
        attr = [f"{key}={val}" for (key, val) in self.__dict__.items() if not key.startswith("_")]
        attr_string = ", ".join(attr)
        return f"{src}({attr_string})"


class User(Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    token: Mapped[str] = mapped_column(String(200))
    global_role: Mapped[str] = mapped_column(String(100))


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(ForeignKey("projects.name", ondelete="CASCADE"))
    project: Mapped["Project"] = relationship()

    user_name: Mapped[str] = mapped_column(ForeignKey("users.name", ondelete="CASCADE"))
    user: Mapped[User] = relationship()

    project_role: Mapped[str] = mapped_column(String(100))


class Project(Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    backend: Mapped[str] = mapped_column(String(30))
    config: Mapped[str] = mapped_column(String(300))
    auth: Mapped[str] = mapped_column(String(300))
    members: Mapped[List[Member]] = relationship(back_populates="project", lazy="selectin")
