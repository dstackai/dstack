import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BLOB,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy_utils import UUIDType

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.runs import JobErrorCode, JobStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.utils.common import get_current_datetime

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

    default_gateway_id: Mapped[Optional[UUIDType]] = mapped_column(
        ForeignKey("gateways.id", use_alter=True, ondelete="SET NULL"), nullable=True
    )
    default_gateway: Mapped["GatewayModel"] = relationship(
        foreign_keys=[default_gateway_id], lazy="selectin"
    )


class MemberModel(BaseModel):
    __tablename__ = "members"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[UUIDType] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    user_id: Mapped[UUIDType] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user: Mapped[UserModel] = relationship(lazy="joined")
    project_role: Mapped[ProjectRole] = mapped_column(Enum(ProjectRole))


class BackendModel(BaseModel):
    __tablename__ = "backends"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[UUIDType] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    type: Mapped[BackendType] = mapped_column(Enum(BackendType))

    config: Mapped[str] = mapped_column(String(2000))
    auth: Mapped[str] = mapped_column(String(2000))

    gateways: Mapped[List["GatewayModel"]] = relationship(back_populates="backend")


class RepoModel(BaseModel):
    __tablename__ = "repos"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[UUIDType] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    # RepoModel.name stores repo_id
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[RepoType] = mapped_column(Enum(RepoType))

    info: Mapped[str] = mapped_column(String(2000))
    creds: Mapped[Optional[str]] = mapped_column(String(2000))

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_repos_project_id_name"),)


class CodeModel(BaseModel):
    __tablename__ = "codes"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[UUIDType] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    repo: Mapped["RepoModel"] = relationship()
    blob_hash: Mapped[str] = mapped_column(String(4000), unique=True)
    blob: Mapped[bytes] = mapped_column(BLOB)


class RunModel(BaseModel):
    __tablename__ = "runs"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[UUIDType] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    repo_id: Mapped[UUIDType] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    repo: Mapped["RepoModel"] = relationship()
    user_id: Mapped["UserModel"] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user: Mapped["UserModel"] = relationship()
    submitted_at: Mapped[datetime] = mapped_column(DateTime)
    run_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus))
    run_spec: Mapped[str] = mapped_column(String(4000))
    jobs: Mapped[List["JobModel"]] = relationship(back_populates="run", lazy="selectin")


class JobModel(BaseModel):
    __tablename__ = "jobs"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[UUIDType] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    run_id: Mapped[UUIDType] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    run_name: Mapped[str] = mapped_column(String(100))
    run: Mapped["RunModel"] = relationship()
    job_num: Mapped[int] = mapped_column(Integer)
    job_name: Mapped[str] = mapped_column(String(100))
    submission_num: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(DateTime)
    last_processed_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus))
    error_code: Mapped[Optional[JobErrorCode]] = mapped_column(Enum(JobErrorCode))
    job_spec_data: Mapped[str] = mapped_column(String(4000))
    job_provisioning_data: Mapped[Optional[str]] = mapped_column(String(4000))
    runner_timestamp: Mapped[Optional[int]] = mapped_column(Integer)


class GatewayModel(BaseModel):
    __tablename__ = "gateways"

    id: Mapped[UUIDType] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str] = mapped_column(String(100))
    instance_id: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(100))
    wildcard_domain: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_current_datetime)

    project_id: Mapped[UUIDType] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship(foreign_keys=[project_id])
    backend_id: Mapped[UUIDType] = mapped_column(ForeignKey("backends.id", ondelete="CASCADE"))
    backend: Mapped["BackendModel"] = relationship(lazy="selectin")

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_gateways_project_id_name"),)
