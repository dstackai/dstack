import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BLOB,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import false
from sqlalchemy_utils import UUIDType

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.profiles import (
    DEFAULT_POOL_TERMINATION_IDLE_TIME,
    TerminationPolicy,
)
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.runs import InstanceStatus, JobErrorCode, JobStatus
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True)
    token: Mapped[str] = mapped_column(String(200), unique=True)
    global_role: Mapped[GlobalRole] = mapped_column(Enum(GlobalRole))

    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    projects_quota: Mapped[int] = mapped_column(Integer, default=3)


class ProjectModel(BaseModel):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    owner: Mapped[UserModel] = relationship(lazy="joined")
    members: Mapped[List["MemberModel"]] = relationship(back_populates="project", lazy="selectin")

    ssh_private_key: Mapped[str] = mapped_column(Text)
    ssh_public_key: Mapped[str] = mapped_column(Text)

    backends: Mapped[List["BackendModel"]] = relationship(
        back_populates="project", lazy="selectin"
    )

    default_gateway_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("gateways.id", use_alter=True, ondelete="SET NULL"), nullable=True
    )
    default_gateway: Mapped["GatewayModel"] = relationship(
        foreign_keys=[default_gateway_id], lazy="selectin"
    )

    default_pool_id: Mapped[Optional[UUIDType]] = mapped_column(
        ForeignKey("pools.id", use_alter=True, ondelete="SET NULL"), nullable=True
    )
    default_pool: Mapped[Optional["PoolModel"]] = relationship(
        foreign_keys=[default_pool_id], lazy="selectin"
    )


class MemberModel(BaseModel):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user: Mapped[UserModel] = relationship(lazy="joined")
    project_role: Mapped[ProjectRole] = mapped_column(Enum(ProjectRole))


class BackendModel(BaseModel):
    __tablename__ = "backends"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    type: Mapped[BackendType] = mapped_column(Enum(BackendType))

    config: Mapped[str] = mapped_column(String(2000))
    auth: Mapped[str] = mapped_column(String(2000))

    gateways: Mapped[List["GatewayModel"]] = relationship(back_populates="backend")


class RepoModel(BaseModel):
    __tablename__ = "repos"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_repos_project_id_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    # RepoModel.name stores repo_id
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[RepoType] = mapped_column(Enum(RepoType))

    info: Mapped[str] = mapped_column(String(2000))
    creds: Mapped[Optional[str]] = mapped_column(String(2000))


class CodeModel(BaseModel):
    __tablename__ = "codes"
    __table_args__ = (UniqueConstraint("repo_id", "blob_hash", name="uq_codes_repo_id_blob_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    repo: Mapped["RepoModel"] = relationship()
    blob_hash: Mapped[str] = mapped_column(String(4000))
    blob: Mapped[Optional[bytes]] = mapped_column(BLOB)  # None means blob is stored on s3


class RunModel(BaseModel):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    repo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    run: Mapped["RunModel"] = relationship()
    run_name: Mapped[str] = mapped_column(String(100))
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
    # `removed` is used to ensure that the instance is killed after the job is finished
    removed: Mapped[bool] = mapped_column(Boolean, default=False)
    remove_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    instance: Mapped[Optional["InstanceModel"]] = relationship(back_populates="job")
    used_instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUIDType(binary=False))


class GatewayModel(BaseModel):
    __tablename__ = "gateways"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(100))
    wildcard_domain: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_current_datetime)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship(foreign_keys=[project_id])
    backend_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backends.id", ondelete="CASCADE"))
    backend: Mapped["BackendModel"] = relationship(lazy="selectin")

    gateway_compute_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("gateway_computes.id", ondelete="CASCADE")
    )
    gateway_compute: Mapped[Optional["GatewayComputeModel"]] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_gateways_project_id_name"),)


class GatewayComputeModel(BaseModel):
    __tablename__ = "gateway_computes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_current_datetime)
    instance_id: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(100))

    backend_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("backends.id", ondelete="CASCADE")
    )
    backend: Mapped[Optional["BackendModel"]] = relationship()

    # The key to authorize the server with the gateway
    ssh_private_key: Mapped[str] = mapped_column(Text)
    ssh_public_key: Mapped[str] = mapped_column(Text)

    deleted: Mapped[bool] = mapped_column(Boolean, server_default=false())


class PoolModel(BaseModel):
    __tablename__ = "pools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_current_datetime)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship(foreign_keys=[project_id])

    instances: Mapped[List["InstanceModel"]] = relationship(back_populates="pool", lazy="selectin")


class InstanceModel(BaseModel):
    __tablename__ = "instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50))

    # instance
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_current_datetime)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship(foreign_keys=[project_id])

    pool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pools.id"))
    pool: Mapped["PoolModel"] = relationship(back_populates="instances")

    status: Mapped[InstanceStatus] = mapped_column(Enum(InstanceStatus))

    # VM
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=get_current_datetime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # temination policy
    termination_policy: Mapped[Optional[TerminationPolicy]] = mapped_column(String(50))
    termination_idle_time: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_POOL_TERMINATION_IDLE_TIME
    )

    # instance termination handling
    termination_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    termination_reason: Mapped[Optional[str]] = mapped_column(String(4000))
    health_status: Mapped[Optional[str]] = mapped_column(String(4000))

    # backend
    backend: Mapped[BackendType] = mapped_column(Enum(BackendType))
    backend_data: Mapped[Optional[str]] = mapped_column(String(4000))

    # offer
    offer: Mapped[str] = mapped_column(String(4000))
    region: Mapped[str] = mapped_column(String(2000))
    price: Mapped[float] = mapped_column(Float)

    job_provisioning_data: Mapped[str] = mapped_column(String(4000))

    # current job
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("jobs.id"))
    job: Mapped[Optional["JobModel"]] = relationship(back_populates="instance", lazy="immediate")
    last_job_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
