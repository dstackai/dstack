import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import false
from sqlalchemy_utils import UUIDType

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import GatewayStatus
from dstack._internal.core.models.profiles import (
    DEFAULT_POOL_TERMINATION_IDLE_TIME,
    TerminationPolicy,
)
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.runs import (
    InstanceStatus,
    JobStatus,
    JobTerminationReason,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server import settings
from dstack._internal.utils.common import get_current_datetime


class NaiveDateTime(TypeDecorator):
    """
    The custom type decorator that ensures datetime objects are offset-naive when stored in the database.
    This is needed because we use datetimes in UTC only and store them as offset-naive.
    Some databases (e.g. Postgres) throw an error if the timezone is set.
    """

    impl = DateTime

    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        return value


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

    projects_quota: Mapped[int] = mapped_column(
        Integer, default=settings.USER_PROJECT_DEFAULT_QUOTA
    )


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
    default_pool: Mapped[Optional["PoolModel"]] = relationship(foreign_keys=[default_pool_id])


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

    config: Mapped[str] = mapped_column(String(20000))
    auth: Mapped[str] = mapped_column(String(20000))

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
    blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary)  # None means blob is stored on s3


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
    submitted_at: Mapped[datetime] = mapped_column(NaiveDateTime)
    run_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus))
    run_spec: Mapped[str] = mapped_column(String(4000))
    jobs: Mapped[List["JobModel"]] = relationship(back_populates="run", lazy="selectin")
    last_processed_at: Mapped[datetime] = mapped_column(NaiveDateTime)
    gateway_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("gateways.id", ondelete="SET NULL")
    )
    gateway: Mapped[Optional["GatewayModel"]] = relationship()
    termination_reason: Mapped[Optional[RunTerminationReason]] = mapped_column(
        Enum(RunTerminationReason)
    )
    service_spec: Mapped[Optional[str]] = mapped_column(String(4000))

    __table_args__ = (Index("ix_submitted_at_id", submitted_at.desc(), id),)


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
    submitted_at: Mapped[datetime] = mapped_column(NaiveDateTime)
    last_processed_at: Mapped[datetime] = mapped_column(NaiveDateTime)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus))
    termination_reason: Mapped[Optional[JobTerminationReason]] = mapped_column(
        Enum(JobTerminationReason)
    )
    termination_reason_message: Mapped[Optional[str]] = mapped_column(Text)
    job_spec_data: Mapped[str] = mapped_column(String(4000))
    job_provisioning_data: Mapped[Optional[str]] = mapped_column(String(4000))
    runner_timestamp: Mapped[Optional[int]] = mapped_column(BigInteger)
    # `removed` is used to ensure that the instance is killed after the job is finished
    remove_at: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)
    instance: Mapped[Optional["InstanceModel"]] = relationship(back_populates="job")
    used_instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUIDType(binary=False))
    replica_num: Mapped[int] = mapped_column(Integer)


class GatewayModel(BaseModel):
    __tablename__ = "gateways"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(100))
    wildcard_domain: Mapped[str] = mapped_column(String(100), nullable=True)
    configuration: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(NaiveDateTime, default=get_current_datetime)
    status: Mapped[GatewayStatus] = mapped_column(Enum(GatewayStatus))
    status_message: Mapped[Optional[str]] = mapped_column(Text)
    last_processed_at: Mapped[datetime] = mapped_column(NaiveDateTime)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship(foreign_keys=[project_id])
    backend_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backends.id", ondelete="CASCADE"))
    backend: Mapped["BackendModel"] = relationship(lazy="selectin")

    gateway_compute_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("gateway_computes.id", ondelete="CASCADE")
    )
    gateway_compute: Mapped[Optional["GatewayComputeModel"]] = relationship(lazy="joined")

    runs: Mapped[List["RunModel"]] = relationship(back_populates="gateway")

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_gateways_project_id_name"),)


class GatewayComputeModel(BaseModel):
    __tablename__ = "gateway_computes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(NaiveDateTime, default=get_current_datetime)
    instance_id: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str] = mapped_column(String(100))
    hostname: Mapped[Optional[str]] = mapped_column(String(100))
    configuration: Mapped[Optional[str]] = mapped_column(Text)
    backend_data: Mapped[Optional[str]] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(100))

    backend_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("backends.id", ondelete="CASCADE")
    )
    backend: Mapped[Optional["BackendModel"]] = relationship()

    # The key to authorize the server with the gateway
    ssh_private_key: Mapped[str] = mapped_column(Text)
    ssh_public_key: Mapped[str] = mapped_column(Text)

    # active means the server should maintain connection to gateway.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, server_default=false())


class PoolModel(BaseModel):
    __tablename__ = "pools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(NaiveDateTime, default=get_current_datetime)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)

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
    created_at: Mapped[datetime] = mapped_column(NaiveDateTime, default=get_current_datetime)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship(foreign_keys=[project_id])

    pool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pools.id"))
    pool: Mapped["PoolModel"] = relationship(back_populates="instances")

    status: Mapped[InstanceStatus] = mapped_column(Enum(InstanceStatus))
    unreachable: Mapped[bool] = mapped_column(Boolean)

    # VM
    started_at: Mapped[Optional[datetime]] = mapped_column(
        NaiveDateTime, default=get_current_datetime
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)

    # create instance
    # TODO: Introduce a field that would store all resolved instance profile parameters, etc, (similar to job_spec).
    # Currently, profile parameters are parsed every time they are accessed (e.g. see profile.retry).
    profile: Mapped[Optional[str]] = mapped_column(Text)
    requirements: Mapped[Optional[str]] = mapped_column(String(10_000))
    instance_configuration: Mapped[Optional[str]] = mapped_column(Text)

    # temination policy
    termination_policy: Mapped[Optional[TerminationPolicy]] = mapped_column(String(50))
    termination_idle_time: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_POOL_TERMINATION_IDLE_TIME
    )

    # retry policy
    last_retry_at: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)

    # instance termination handling
    termination_deadline: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)
    termination_reason: Mapped[Optional[str]] = mapped_column(String(4000))
    health_status: Mapped[Optional[str]] = mapped_column(String(4000))

    # backend
    backend: Mapped[Optional[BackendType]] = mapped_column(Enum(BackendType))
    backend_data: Mapped[Optional[str]] = mapped_column(String(4000))

    # offer
    offer: Mapped[Optional[str]] = mapped_column(String(4000))
    region: Mapped[Optional[str]] = mapped_column(String(2000))
    price: Mapped[Optional[float]] = mapped_column(Float)

    job_provisioning_data: Mapped[Optional[str]] = mapped_column(String(4000))

    remote_connection_info: Mapped[Optional[str]] = mapped_column(Text)

    # current job
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("jobs.id"))
    job: Mapped[Optional["JobModel"]] = relationship(back_populates="instance", lazy="joined")
    last_job_processed_at: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)

    # volumes attached to the instance
    volumes: Mapped[List["VolumeModel"]] = relationship(
        secondary="volumes_attachments",
        back_populates="instances",
    )


class VolumeModel(BaseModel):
    __tablename__ = "volumes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(binary=False), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100))

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    project: Mapped["ProjectModel"] = relationship(foreign_keys=[project_id])

    created_at: Mapped[datetime] = mapped_column(NaiveDateTime, default=get_current_datetime)
    last_processed_at: Mapped[datetime] = mapped_column(
        NaiveDateTime, default=get_current_datetime
    )
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)

    status: Mapped[VolumeStatus] = mapped_column(Enum(VolumeStatus))
    status_message: Mapped[Optional[str]] = mapped_column(Text)

    configuration: Mapped[str] = mapped_column(Text)
    volume_provisioning_data: Mapped[Optional[str]] = mapped_column(Text)
    volume_attachment_data: Mapped[Optional[str]] = mapped_column(Text)

    # instances the volume is attached to
    instances: Mapped[List["InstanceModel"]] = relationship(
        secondary="volumes_attachments",
        back_populates="volumes",
    )


volumes_attachments_table = Table(
    "volumes_attachments",
    BackendModel.metadata,
    Column("volume_id", ForeignKey("volumes.id"), primary_key=True),
    Column("instace_id", ForeignKey("instances.id"), primary_key=True),
)
