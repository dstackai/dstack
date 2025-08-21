from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Type
from urllib.parse import urlparse

from pydantic import UUID4, Field, root_validator
from typing_extensions import Annotated

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import ApplyAction, CoreModel, NetworkMode, RegistryAuth
from dstack._internal.core.models.configurations import (
    DEFAULT_PROBE_METHOD,
    DEFAULT_REPO_DIR,
    AnyRunConfiguration,
    HTTPHeaderSpec,
    HTTPMethod,
    RunConfiguration,
    ServiceConfiguration,
)
from dstack._internal.core.models.files import FileArchiveMapping
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceType,
    SSHConnectionParams,
)
from dstack._internal.core.models.profiles import (
    CreationPolicy,
    Profile,
    ProfileParams,
    RetryEvent,
    SpotPolicy,
    UtilizationPolicy,
)
from dstack._internal.core.models.repos import AnyRunRepoData
from dstack._internal.core.models.resources import Memory, ResourcesSpec
from dstack._internal.core.models.unix import UnixUser
from dstack._internal.core.models.volumes import MountPoint
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.common import format_pretty_duration


class AppSpec(CoreModel):
    port: int
    map_to_port: Optional[int]
    app_name: str
    url_path: Optional[str] = None
    url_query_params: Optional[Dict[str, str]] = None


class JobStatus(str, Enum):
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    PULLING = "pulling"
    RUNNING = "running"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ABORTED = "aborted"
    FAILED = "failed"
    DONE = "done"

    @classmethod
    def finished_statuses(cls) -> List["JobStatus"]:
        return [cls.TERMINATED, cls.ABORTED, cls.FAILED, cls.DONE]

    def is_finished(self):
        return self in self.finished_statuses()


class Retry(CoreModel):
    on_events: List[RetryEvent]
    duration: int

    def pretty_format(self) -> str:
        pretty_duration = format_pretty_duration(self.duration)
        events = ", ".join(event.value for event in self.on_events)
        return f"{pretty_duration}[{events}]"


class RunTerminationReason(str, Enum):
    ALL_JOBS_DONE = "all_jobs_done"
    JOB_FAILED = "job_failed"
    RETRY_LIMIT_EXCEEDED = "retry_limit_exceeded"
    STOPPED_BY_USER = "stopped_by_user"
    ABORTED_BY_USER = "aborted_by_user"
    SERVER_ERROR = "server_error"

    def to_job_termination_reason(self) -> "JobTerminationReason":
        mapping = {
            self.ALL_JOBS_DONE: JobTerminationReason.DONE_BY_RUNNER,
            self.JOB_FAILED: JobTerminationReason.TERMINATED_BY_SERVER,
            self.RETRY_LIMIT_EXCEEDED: JobTerminationReason.TERMINATED_BY_SERVER,
            self.STOPPED_BY_USER: JobTerminationReason.TERMINATED_BY_USER,
            self.ABORTED_BY_USER: JobTerminationReason.ABORTED_BY_USER,
            self.SERVER_ERROR: JobTerminationReason.TERMINATED_BY_SERVER,
        }
        return mapping[self]

    def to_status(self) -> "RunStatus":
        mapping = {
            self.ALL_JOBS_DONE: RunStatus.DONE,
            self.JOB_FAILED: RunStatus.FAILED,
            self.RETRY_LIMIT_EXCEEDED: RunStatus.FAILED,
            self.STOPPED_BY_USER: RunStatus.TERMINATED,
            self.ABORTED_BY_USER: RunStatus.TERMINATED,
            self.SERVER_ERROR: RunStatus.FAILED,
        }
        return mapping[self]

    def to_error(self) -> Optional[str]:
        if self == RunTerminationReason.RETRY_LIMIT_EXCEEDED:
            return "retry limit exceeded"
        elif self == RunTerminationReason.SERVER_ERROR:
            return "server error"
        else:
            return None


class JobTerminationReason(str, Enum):
    # Set by the server
    FAILED_TO_START_DUE_TO_NO_CAPACITY = "failed_to_start_due_to_no_capacity"
    INTERRUPTED_BY_NO_CAPACITY = "interrupted_by_no_capacity"
    INSTANCE_UNREACHABLE = "instance_unreachable"
    WAITING_INSTANCE_LIMIT_EXCEEDED = "waiting_instance_limit_exceeded"
    WAITING_RUNNER_LIMIT_EXCEEDED = "waiting_runner_limit_exceeded"
    TERMINATED_BY_USER = "terminated_by_user"
    VOLUME_ERROR = "volume_error"
    GATEWAY_ERROR = "gateway_error"
    SCALED_DOWN = "scaled_down"
    DONE_BY_RUNNER = "done_by_runner"
    ABORTED_BY_USER = "aborted_by_user"
    TERMINATED_BY_SERVER = "terminated_by_server"
    INACTIVITY_DURATION_EXCEEDED = "inactivity_duration_exceeded"
    TERMINATED_DUE_TO_UTILIZATION_POLICY = "terminated_due_to_utilization_policy"
    # Set by the runner
    CONTAINER_EXITED_WITH_ERROR = "container_exited_with_error"
    PORTS_BINDING_FAILED = "ports_binding_failed"
    CREATING_CONTAINER_ERROR = "creating_container_error"
    EXECUTOR_ERROR = "executor_error"
    MAX_DURATION_EXCEEDED = "max_duration_exceeded"

    def to_status(self) -> JobStatus:
        mapping = {
            self.FAILED_TO_START_DUE_TO_NO_CAPACITY: JobStatus.FAILED,
            self.INTERRUPTED_BY_NO_CAPACITY: JobStatus.FAILED,
            self.INSTANCE_UNREACHABLE: JobStatus.FAILED,
            self.WAITING_INSTANCE_LIMIT_EXCEEDED: JobStatus.FAILED,
            self.WAITING_RUNNER_LIMIT_EXCEEDED: JobStatus.FAILED,
            self.TERMINATED_BY_USER: JobStatus.TERMINATED,
            self.VOLUME_ERROR: JobStatus.FAILED,
            self.GATEWAY_ERROR: JobStatus.FAILED,
            self.SCALED_DOWN: JobStatus.TERMINATED,
            self.DONE_BY_RUNNER: JobStatus.DONE,
            self.ABORTED_BY_USER: JobStatus.ABORTED,
            self.TERMINATED_BY_SERVER: JobStatus.TERMINATED,
            self.INACTIVITY_DURATION_EXCEEDED: JobStatus.TERMINATED,
            self.TERMINATED_DUE_TO_UTILIZATION_POLICY: JobStatus.TERMINATED,
            self.CONTAINER_EXITED_WITH_ERROR: JobStatus.FAILED,
            self.PORTS_BINDING_FAILED: JobStatus.FAILED,
            self.CREATING_CONTAINER_ERROR: JobStatus.FAILED,
            self.EXECUTOR_ERROR: JobStatus.FAILED,
            self.MAX_DURATION_EXCEEDED: JobStatus.TERMINATED,
        }
        return mapping[self]

    def to_retry_event(self) -> Optional[RetryEvent]:
        """
        Returns:
            the retry event this termination reason triggers
            or None if this termination reason should not be retried
        """
        mapping = {
            self.FAILED_TO_START_DUE_TO_NO_CAPACITY: RetryEvent.NO_CAPACITY,
            self.INTERRUPTED_BY_NO_CAPACITY: RetryEvent.INTERRUPTION,
        }
        default = RetryEvent.ERROR if self.to_status() == JobStatus.FAILED else None
        return mapping.get(self, default)

    def to_error(self) -> Optional[str]:
        # Should return None for values that are already
        # handled and shown in status_message.
        error_mapping = {
            JobTerminationReason.INSTANCE_UNREACHABLE: "instance unreachable",
            JobTerminationReason.WAITING_INSTANCE_LIMIT_EXCEEDED: "waiting instance limit exceeded",
            JobTerminationReason.VOLUME_ERROR: "volume error",
            JobTerminationReason.GATEWAY_ERROR: "gateway error",
            JobTerminationReason.SCALED_DOWN: "scaled down",
            JobTerminationReason.INACTIVITY_DURATION_EXCEEDED: "inactivity duration exceeded",
            JobTerminationReason.TERMINATED_DUE_TO_UTILIZATION_POLICY: "utilization policy",
            JobTerminationReason.PORTS_BINDING_FAILED: "ports binding failed",
            JobTerminationReason.CREATING_CONTAINER_ERROR: "runner error",
            JobTerminationReason.EXECUTOR_ERROR: "executor error",
            JobTerminationReason.MAX_DURATION_EXCEEDED: "max duration exceeded",
        }
        return error_mapping.get(self)


class Requirements(CoreModel):
    # TODO: Make requirements' fields required
    resources: ResourcesSpec
    max_price: Optional[float] = None
    spot: Optional[bool] = None
    reservation: Optional[str] = None

    def pretty_format(self, resources_only: bool = False):
        res = self.resources.pretty_format()
        if not resources_only:
            if self.spot is not None:
                res += f", {'spot' if self.spot else 'on-demand'}"
            if self.max_price is not None:
                res += f" under ${self.max_price:3f}".rstrip("0").rstrip(".") + " per hour"
        return res


class Gateway(CoreModel):
    gateway_name: Optional[str]
    service_port: int
    hostname: Optional[str]
    public_port: int = 80
    secure: bool = False

    auth: bool = True
    options: dict = {}


class JobSSHKey(CoreModel):
    private: str
    public: str


class ProbeSpec(CoreModel):
    type: Literal["http"]  # expect other probe types in the future, namely `exec`
    url: str
    method: HTTPMethod = DEFAULT_PROBE_METHOD
    headers: list[HTTPHeaderSpec] = []
    body: Optional[str] = None
    timeout: int
    interval: int
    ready_after: int


class JobSpec(CoreModel):
    replica_num: int = 0  # default value for backward compatibility
    job_num: int
    job_name: str
    jobs_per_replica: int = 1  # default value for backward compatibility
    app_specs: Optional[List[AppSpec]]
    user: Optional[UnixUser] = None  # default value for backward compatibility
    commands: List[str]
    env: Dict[str, str]
    home_dir: Optional[str]
    image_name: str
    privileged: bool = False
    single_branch: Optional[bool] = None
    max_duration: Optional[int]
    stop_duration: Optional[int] = None
    utilization_policy: Optional[UtilizationPolicy] = None
    registry_auth: Optional[RegistryAuth]
    requirements: Requirements
    retry: Optional[Retry]
    volumes: Optional[List[MountPoint]] = None
    ssh_key: Optional[JobSSHKey] = None
    working_dir: Optional[str]
    # `repo_data` is optional for client compatibility with pre-0.19.17 servers and for compatibility
    # with jobs submitted before 0.19.17. All new jobs are expected to have non-None `repo_data`.
    # For --no-repo runs, `repo_data` is `VirtualRunRepoData()`.
    repo_data: Annotated[Optional[AnyRunRepoData], Field(discriminator="repo_type")] = None
    # `repo_code_hash` can be None because it is not used for the repo or because the job was
    # submitted before 0.19.17. See `_get_repo_code_hash` on how to get the correct `repo_code_hash`
    # TODO: drop this comment when supporting jobs submitted before 0.19.17 is no longer relevant.
    repo_code_hash: Optional[str] = None
    file_archives: list[FileArchiveMapping] = []
    # None for non-services and pre-0.19.19 services. See `get_service_port`
    service_port: Optional[int] = None
    probes: list[ProbeSpec] = []


class JobProvisioningData(CoreModel):
    backend: BackendType
    # In case backend provisions instance in another backend, it may set that backend as base_backend.
    base_backend: Optional[BackendType] = None
    instance_type: InstanceType
    instance_id: str
    # hostname may not be set immediately after instance provisioning.
    # It is set to a public IP or, if public IPs are disabled, to a private IP.
    hostname: Optional[str] = None
    internal_ip: Optional[str] = None
    # public_ip_enabled can used to distinguished instances with and without public IPs.
    # hostname being None is not enough since it can be filled after provisioning.
    public_ip_enabled: bool = True
    # instance_network a network address for multimode installation. Specified as `<ip address>/<netmask>`
    # internal_ip will be selected from the specified network
    instance_network: Optional[str] = None
    region: str
    availability_zone: Optional[str] = None
    reservation: Optional[str] = None
    price: float
    username: str
    # ssh_port be different from 22 for some backends.
    # ssh_port may not be set immediately after instance provisioning
    ssh_port: Optional[int] = None
    dockerized: bool  # True if backend starts shim
    ssh_proxy: Optional[SSHConnectionParams] = None
    backend_data: Optional[str] = None  # backend-specific data in json

    def get_base_backend(self) -> BackendType:
        if self.base_backend is not None:
            return self.base_backend
        return self.backend


class JobRuntimeData(CoreModel):
    """
    Holds various information only available after the job is submitted, such as:
        * offer (depends on the instance)
        * volumes used by the job
        * resource constraints for container (depend on the instance)
        * port mapping (reported by the shim only after the container is started)

    Some fields are mutable, for example, `ports` only available when the shim starts
    the container.
    """

    network_mode: NetworkMode
    # GPU, CPU, memory resource shares. None means all available (no limit)
    gpu: Optional[int] = None
    cpu: Optional[float] = None
    memory: Optional[Memory] = None
    # container:host port mapping reported by shim. Empty dict if network_mode == NetworkMode.HOST
    # None if data is not yet available (on vm-based backends and ssh instances)
    # or not applicable (container-based backends)
    ports: Optional[dict[int, int]] = None
    # List of volumes used by the job
    volume_names: Optional[list[str]] = None  # None for backward compatibility
    # Virtual shared offer
    offer: Optional[InstanceOfferWithAvailability] = None  # None for backward compatibility


class ClusterInfo(CoreModel):
    job_ips: List[str]
    master_job_ip: str
    gpus_per_job: int


class Probe(CoreModel):
    success_streak: int


class JobSubmission(CoreModel):
    id: UUID4
    submission_num: int
    deployment_num: int = 0  # default for compatibility with pre-0.19.14 servers
    submitted_at: datetime
    last_processed_at: datetime
    finished_at: Optional[datetime] = None
    inactivity_secs: Optional[int] = None
    status: JobStatus
    status_message: str = ""  # default for backward compatibility
    # termination_reason stores JobTerminationReason.
    # str allows adding new enum members without breaking compatibility with old clients.
    termination_reason: Optional[str] = None
    termination_reason_message: Optional[str] = None
    exit_status: Optional[int] = None
    job_provisioning_data: Optional[JobProvisioningData] = None
    job_runtime_data: Optional[JobRuntimeData] = None
    error: Optional[str] = None
    probes: list[Probe] = []

    @property
    def age(self) -> timedelta:
        return common_utils.get_current_datetime() - self.submitted_at

    @property
    def duration(self) -> timedelta:
        end_time = common_utils.get_current_datetime()
        if self.finished_at is not None:
            end_time = self.finished_at
        return end_time - self.submitted_at


class Job(CoreModel):
    job_spec: JobSpec
    job_submissions: List[JobSubmission]


class RunSpec(CoreModel):
    # TODO: run_name, working_dir are redundant here since they already passed in configuration
    run_name: Annotated[
        Optional[str],
        Field(description="The run name. If not set, the run name is generated automatically."),
    ] = None
    repo_id: Annotated[
        Optional[str],
        Field(
            description=(
                "Same `repo_id` that is specified when initializing the repo"
                " by calling the `/api/project/{project_name}/repos/init` endpoint."
                " If not specified, a default virtual repo is used."
            )
        ),
    ] = None
    repo_data: Annotated[
        Optional[AnyRunRepoData],
        Field(
            discriminator="repo_type",
            description="The repo data such as the current branch and commit.",
        ),
    ] = None
    repo_code_hash: Annotated[
        Optional[str],
        Field(description="The hash of the repo diff. Can be omitted if there is no repo diff."),
    ] = None
    file_archives: Annotated[
        list[FileArchiveMapping],
        Field(description="The list of file archive ID to container path mappings"),
    ] = []
    working_dir: Annotated[
        Optional[str],
        Field(
            description=(
                "The path to the working directory inside the container."
                f" It's specified relative to the repository directory (`{DEFAULT_REPO_DIR}`) and should be inside it."
                ' Defaults to `"."`.'
            )
        ),
    ] = None
    configuration_path: Annotated[
        Optional[str],
        Field(
            description=(
                "The path to the run configuration YAML file."
                " It can be omitted when using the programmatic API."
            )
        ),
    ] = None
    configuration: Annotated[AnyRunConfiguration, Field(discriminator="type")]
    profile: Annotated[Optional[Profile], Field(description="The profile parameters")] = None
    ssh_key_pub: Annotated[
        str,
        Field(
            description="The contents of the SSH public key that will be used to connect to the run."
        ),
    ]
    # merged_profile stores profile parameters merged from profile and configuration.
    # Read profile parameters from merged_profile instead of profile directly.
    # TODO: make merged_profile a computed field after migrating to pydanticV2
    merged_profile: Annotated[Profile, Field(exclude=True)] = None

    class Config(CoreModel.Config):
        @staticmethod
        def schema_extra(schema: Dict[str, Any], model: Type) -> None:
            prop = schema.get("properties", {})
            prop.pop("merged_profile", None)

    @root_validator
    def _merged_profile(cls, values) -> Dict:
        if values.get("profile") is None:
            merged_profile = Profile(name="default")
        else:
            merged_profile = Profile.parse_obj(values["profile"])
        try:
            conf = RunConfiguration.parse_obj(values["configuration"]).__root__
        except KeyError:
            raise ValueError("Missing configuration")
        for key in ProfileParams.__fields__:
            conf_val = getattr(conf, key, None)
            if conf_val is not None:
                setattr(merged_profile, key, conf_val)
        if merged_profile.creation_policy is None:
            merged_profile.creation_policy = CreationPolicy.REUSE_OR_CREATE
        values["merged_profile"] = merged_profile
        return values


class ServiceModelSpec(CoreModel):
    name: str
    base_url: Annotated[
        str, Field(description="Full URL or path relative to dstack-server's base URL")
    ]
    type: str


class ServiceSpec(CoreModel):
    url: Annotated[str, Field(description="Full URL or path relative to dstack-server's base URL")]
    model: Optional[ServiceModelSpec] = None
    options: Dict[str, Any] = {}

    def get_domain(self) -> Optional[str]:
        return urlparse(self.url).hostname


class RunStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"
    DONE = "done"

    @classmethod
    def finished_statuses(cls) -> List["RunStatus"]:
        return [cls.TERMINATED, cls.FAILED, cls.DONE]

    def is_finished(self):
        return self in self.finished_statuses()


class Run(CoreModel):
    id: UUID4
    project_name: str
    user: str
    submitted_at: datetime
    last_processed_at: datetime
    status: RunStatus
    status_message: str = ""  # default for backward compatibility
    # termination_reason stores RunTerminationReason.
    # str allows adding new enum members without breaking compatibility with old clients.
    termination_reason: Optional[str] = None
    run_spec: RunSpec
    jobs: List[Job]
    latest_job_submission: Optional[JobSubmission] = None
    cost: float = 0
    service: Optional[ServiceSpec] = None
    deployment_num: int = 0  # default for compatibility with pre-0.19.14 servers
    error: Optional[str] = None
    deleted: Optional[bool] = None

    def is_deployment_in_progress(self) -> bool:
        return any(
            not j.job_submissions[-1].status.is_finished()
            and j.job_submissions[-1].deployment_num != self.deployment_num
            for j in self.jobs
        )


class JobPlan(CoreModel):
    job_spec: JobSpec
    offers: List[InstanceOfferWithAvailability]
    total_offers: int
    max_price: Optional[float]


class RunPlan(CoreModel):
    project_name: str
    user: str
    run_spec: RunSpec
    effective_run_spec: Optional[RunSpec] = None
    job_plans: List[JobPlan]
    current_resource: Optional[Run] = None
    action: ApplyAction

    def get_effective_run_spec(self) -> RunSpec:
        if self.effective_run_spec is not None:
            return self.effective_run_spec
        return self.run_spec


class ApplyRunPlanInput(CoreModel):
    run_spec: RunSpec
    current_resource: Annotated[
        Optional[Run],
        Field(
            description=(
                "The expected current resource."
                " If the resource has changed, the apply fails unless `force: true`."
            )
        ),
    ] = None


def get_policy_map(spot_policy: Optional[SpotPolicy], default: SpotPolicy) -> Optional[bool]:
    """
    Map profile.spot_policy[SpotPolicy|None] to requirements.spot[bool|None]
    """
    if spot_policy is None:
        spot_policy = default
    policy_map = {
        SpotPolicy.AUTO: None,
        SpotPolicy.SPOT: True,
        SpotPolicy.ONDEMAND: False,
    }
    return policy_map[spot_policy]


def get_service_port(job_spec: JobSpec, configuration: ServiceConfiguration) -> int:
    # Compatibility with pre-0.19.19 job specs that do not have the `service_port` property.
    # TODO: drop when pre-0.19.19 jobs are no longer relevant.
    if job_spec.service_port is None:
        return configuration.port.container_port
    return job_spec.service_port
