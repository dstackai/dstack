from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from dstack.hub.db import Base


class User(Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    token: Mapped[str] = mapped_column(String(30))

    def __repr__(self) -> str:
        return f"User(name={self.name!r}, token={self.token!r})"
