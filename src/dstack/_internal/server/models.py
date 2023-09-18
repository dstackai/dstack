import uuid
from typing import List

from sqlalchemy import Enum, ForeignKey, MetaData, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy_utils import UUIDType

from dstack._internal.core.models.backends import BackendType
from dstack._internal.core.models.users import GlobalRole, ProjectRole

constraint_naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class BaseModel(DeclarativeBase):
    metadata = MetaData(naming_convention=constraint_naming_convention)


class UserModel(BaseModel):
    __tablename__ = "users"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True)
    token: Mapped[str] = mapped_column(String(200), unique=True)
    global_role: Mapped[GlobalRole] = mapped_column(Enum(GlobalRole))


class ProjectModel(BaseModel):
    __tablename__ = "projects"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True)
    members: Mapped[List["MemberModel"]] = relationship(back_populates="project", lazy="selectin")

    ssh_private_key: Mapped[str] = mapped_column(Text)
    ssh_public_key: Mapped[str] = mapped_column(Text)

    backends: Mapped[List["BackendModel"]] = relationship(
        back_populates="project", lazy="selectin"
    )


class MemberModel(BaseModel):
    __tablename__ = "members"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user: Mapped[UserModel] = relationship()
    project_role: Mapped[ProjectRole] = mapped_column(Enum(ProjectRole))


class BackendModel(BaseModel):
    __tablename__ = "backends"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    type: Mapped[BackendType] = mapped_column(Enum(BackendType))

    config: Mapped[str] = mapped_column(String(2000))
    auth: Mapped[str] = mapped_column(String(2000))


# class Job(BaseModel):
#     """
#     This table stores not started jobs that are not stored in any backend.
#     After the job is successfully submitted to a backed, it is deleted from the table.
#     """

#     __tablename__ = "jobs"

#     job_id: Mapped[str] = mapped_column(String(50), primary_key=True)
#     run_name = mapped_column(String(50), index=True)
#     project_name: Mapped[str] = mapped_column(ForeignKey("projects.name", ondelete="CASCADE"))
#     project: Mapped["ProjectModel"] = relationship()
#     status: Mapped[str] = mapped_column(String(30), index=True)
#     job_data: Mapped[str] = mapped_column(Text)
