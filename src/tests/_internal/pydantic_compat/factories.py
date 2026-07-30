"""
Deterministic model instances for the comparison fixtures.
"""

import uuid
from datetime import datetime, timezone

from dstack._internal.core.backends.aws.models import AWSCreds
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import (
    ApplyAction,
    EntityReference,
    NetworkMode,
)
from dstack._internal.core.models.compute_groups import ComputeGroupProvisioningData
from dstack._internal.core.models.configurations import (
    DevEnvironmentConfiguration,
    PythonVersion,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.fleets import (
    Fleet,
    FleetPlan,
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.gateways import (
    Gateway,
    GatewayComputeConfiguration,
    GatewayConfiguration,
    GatewaySpec,
    GatewayStatus,
)
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    Instance,
    InstanceConfiguration,
    InstanceOffer,
    InstanceStatus,
    RemoteConnectionInfo,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.placement import (
    PlacementGroupConfiguration,
    PlacementGroupProvisioningData,
)
from dstack._internal.core.models.profiles import (
    CreationPolicy,
    Profile,
    ProfileRetry,
    RetryEvent,
    Schedule,
    SpotPolicy,
    StartupOrder,
    StopCriteria,
)
from dstack._internal.core.models.projects import (
    Member,
    MemberPermissions,
    Project,
    ProjectRole,
)
from dstack._internal.core.models.repos.remote import RemoteRepoCreds, RemoteRepoInfo
from dstack._internal.core.models.resources import (
    ComputeCapability,
    DiskSpec,
    GPUSpec,
    Memory,
    Range,
    ResourcesSpec,
)
from dstack._internal.core.models.runs import (
    ImagePullProgress,
    Job,
    JobPlan,
    JobProvisioningData,
    JobRuntimeData,
    JobSpec,
    JobStatus,
    JobSubmission,
    Requirements,
    Run,
    RunPlan,
    RunSpec,
    RunStatus,
    ServiceSpec,
)
from dstack._internal.core.models.secrets import Secret
from dstack._internal.core.models.server import ServerInfo
from dstack._internal.core.models.users import (
    GlobalRole,
    User,
    UserPermissions,
    UserTokenCreds,
    UserWithCreds,
)
from dstack._internal.core.models.volumes import (
    Volume,
    VolumeAttachmentData,
    VolumeConfiguration,
    VolumeProvisioningData,
)
from dstack._internal.proxy.gateway.schemas.registry import RegisterEntrypointRequest
from dstack._internal.proxy.gateway.schemas.stats import ServiceStats, Stat
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsChunkChoice,
    ChatCompletionsRequest,
    ChatMessage,
    Model,
    ModelsResponse,
)
from dstack._internal.server.schemas.fleets import (
    ApplyFleetPlanInput,
    ApplyFleetPlanRequest,
    DeleteFleetsRequest,
)
from dstack._internal.server.schemas.gateways import (
    ApplyGatewayPlanInput,
    ApplyGatewayPlanRequest,
)
from dstack._internal.server.schemas.repos import SaveRepoCredsRequest
from dstack._internal.server.schemas.runner import (
    ComponentInstallRequest,
    ComponentName,
    HealthcheckResponse,
    InstanceHealthResponse,
    JobInfoResponse,
    LegacySubmitBody,
    ShutdownRequest,
    SubmitBody,
    TaskInfoResponse,
    TaskStatus,
    TaskSubmitRequest,
    TaskTerminateRequest,
)
from dstack._internal.server.schemas.runs import (
    ApplyRunPlanInput,
    ApplyRunPlanRequest,
)
from dstack._internal.server.schemas.volumes import CreateVolumeRequest
from dstack._internal.server.testing.common import (
    get_compute_group_provisioning_data,
    get_fleet_configuration,
    get_fleet_spec,
    get_gateway_compute_configuration,
    get_instance_configuration,
    get_instance_offer_with_availability,
    get_job_provisioning_data,
    get_job_runtime_data,
    get_placement_group_configuration,
    get_placement_group_provisioning_data,
    get_remote_connection_info,
    get_run_spec,
    get_volume,
    get_volume_configuration,
    get_volume_provisioning_data,
)

# Version-4 shaped: several models annotate their id as `UUID4`, which validates the version.
_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_CREATED_AT = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


# --- DB blobs ------------------------------------------------------------------------
# Written to a `Text` column with `.json()`.


def aws_creds() -> AWSCreds:
    """A custom-root discriminated union, read from `BackendModel.auth`."""
    return AWSCreds.parse_obj({"type": "access_key", "access_key": "AK", "secret_key": "SK"})


def compute_group_provisioning_data() -> ComputeGroupProvisioningData:
    return get_compute_group_provisioning_data()


def fleet_spec() -> FleetSpec:
    """
    Fills the optional configuration fields: unfilled they serialize as ~34 nulls, and a null
    cannot drift, so the fixture would pin almost nothing.
    """
    spec = get_fleet_spec(
        conf=get_fleet_configuration(
            backends=[BackendType.AWS],
            placement=InstanceGroupPlacement.CLUSTER,
        ),
        profile=profile(),
    )
    conf = spec.configuration
    conf.regions = ["us-east-1"]
    conf.availability_zones = ["us-east-1a"]
    conf.instance_types = ["p4d.24xlarge"]
    conf.reservation = "test-reservation"
    conf.spot_policy = SpotPolicy.AUTO
    conf.idle_duration = 600
    conf.max_price = 25.5
    conf.tags = {"env": "test"}
    conf.resources = ResourcesSpec(
        cpu=Range[int](min=2, max=8),
        memory=Range[Memory](min=Memory(16), max=None),
    )
    return spec


def gateway_compute_configuration() -> GatewayComputeConfiguration:
    return get_gateway_compute_configuration()


def gateway_configuration() -> GatewayConfiguration:
    return GatewayConfiguration(
        name="test-gateway",
        backend=BackendType.AWS,
        region="us-east-1",
        domain="example.com",
    )


def image_pull_progress() -> ImagePullProgress:
    return ImagePullProgress(
        downloaded_bytes=1024,
        extracted_bytes=512,
        total_bytes=4096,
        is_total_bytes_final=True,
    )


def instance_configuration() -> InstanceConfiguration:
    conf = get_instance_configuration()
    conf.instance_id = "i-1234567890abcdef0"
    conf.reservation = "test-reservation"
    conf.tags = {"env": "test"}
    conf.ssh_keys = [SSHKey(public="ssh-rsa PUBLIC", private=None)]
    return conf


def instance_offer() -> InstanceOffer:
    return get_instance_offer_with_availability()


def job_provisioning_data() -> JobProvisioningData:
    return get_job_provisioning_data(
        dockerized=True,
        availability_zone="us-east-1a",
        gpu_count=1,
    )


def job_runtime_data() -> JobRuntimeData:
    """`ports` is a `dict[int, int]` — the only non-str dict keys in the models."""
    data = get_job_runtime_data()
    data.ports = {8080: 30080, 8081: 30081}
    data.network_mode = NetworkMode.HOST
    data.cpu = 2.0
    data.gpu = 1
    data.memory = float(16 * 1024**3)
    data.volume_names = ["test-volume"]
    data.working_dir = "/workflow"
    data.username = "ubuntu"
    return data


def job_spec() -> JobSpec:
    return JobSpec(
        job_num=0,
        job_name="test-run-0-0",
        commands=["/bin/bash", "-i", "-c", "echo hi"],
        env=Env.parse_obj({"A": "1"}),
        image_name="dstackai/base:latest",
        requirements=requirements(),
        max_duration=7200,
        working_dir="/workflow",
    )


def placement_group_configuration() -> PlacementGroupConfiguration:
    return get_placement_group_configuration()


def placement_group_provisioning_data() -> PlacementGroupProvisioningData:
    return get_placement_group_provisioning_data()


def profile() -> Profile:
    return Profile(
        name="default",
        backends=[BackendType.AWS, BackendType.GCP],
        regions=["us-east-1", "eu-west-1"],
        availability_zones=["us-east-1a"],
        instance_types=["p4d.24xlarge"],
        reservation="test-reservation",
        spot_policy=SpotPolicy.AUTO,
        retry=ProfileRetry(on_events=[RetryEvent.NO_CAPACITY], duration=3600),
        max_duration=7200,
        stop_duration=300,
        idle_duration=600,
        max_price=25.5,
        creation_policy=CreationPolicy.REUSE_OR_CREATE,
        stop_criteria=StopCriteria.ALL_DONE,
        startup_order=StartupOrder.MASTER_FIRST,
        fleets=[EntityReference(project=None, name="test-fleet")],
        tags={"env": "test", "team": "core"},
        schedule=Schedule(cron=["0 0 * * *"]),
    )


def remote_connection_info() -> RemoteConnectionInfo:
    return get_remote_connection_info()


def requirements() -> Requirements:
    """Carries `ComputeCapability`, a `Tuple[int, int]` subclass nothing else covers."""
    return Requirements(
        resources=ResourcesSpec(
            cpu=Range[int](min=2, max=8),
            memory=Range[Memory](min=Memory(16), max=None),
            gpu=GPUSpec(
                name=["A100"],
                count=Range[int](min=1, max=1),
                memory=Range[Memory](min=Memory(40), max=None),
                compute_capability=ComputeCapability((8, 0)),
            ),
        ),
        max_price=10.5,
        spot=False,
        reservation="test-reservation",
    )


def resources() -> Resources:
    """`Resources.dict()` rewrites `cpu` for old clients — the other custom serializer."""
    return Resources(
        cpus=8,
        memory_mib=16384,
        gpus=[Gpu(name="A100", memory_mib=40960)],
        spot=False,
        disk=Disk(size_mib=102400),
        description="8xCPU, 16GB, 1xA100",
    )


def run_spec() -> RunSpec:
    """
    Values are given in their already-parsed form rather than as YAML shorthand (`"2h"`,
    `"16GB.."`): shorthand only type-checks because a `pre=True` validator widens the input, and
    pinning the *parse* side is the job of the parsing fixtures, not these.
    """
    return get_run_spec(
        repo_id="test-repo",
        profile=profile(),
        configuration=DevEnvironmentConfiguration(
            name="test-dev",
            ide="vscode",
            version="1.85.0",
            user="ubuntu",
            privileged=False,
            # `image` is deliberately absent: it is mutually exclusive with `python`, and `python`
            # is the more valuable of the two to pin because it is a str enum fed by a YAML float.
            python=PythonVersion.PY311,
            env=Env.parse_obj({"HF_TOKEN": "secret"}),
            working_dir="/workflow",
            inactivity_duration=3600,
            resources=ResourcesSpec(
                cpu=Range[int](min=2, max=8),
                memory=Range[Memory](min=Memory(16), max=None),
                shm_size=Memory(1024),
                disk=DiskSpec(size=Range[Memory](min=Memory(100), max=None)),
            ),
        ),
    )


def service_spec() -> ServiceSpec:
    return ServiceSpec(url="/proxy/services/test-project/test-run/", model=None, options={})


def volume_attachment_data() -> VolumeAttachmentData:
    return VolumeAttachmentData(device_name="/dev/sdb")


def volume_configuration() -> VolumeConfiguration:
    return get_volume_configuration()


def volume_provisioning_data() -> VolumeProvisioningData:
    return get_volume_provisioning_data()


# --- API responses -------------------------------------------------------------------
# Returned from a router through `CustomORJSONResponse`. Chosen by greedy set cover so that
# between them they reach every model class reachable from any response model — 129 of 129.
# `run` and `instance` are absent on purpose: `run_plan` and `fleet` already reach everything
# they would add.


def fleet() -> Fleet:
    """
    The default `FleetNodesSpec` has `target == min`, which is what makes `FleetNodesSpec.dict()`
    drop `target` — the old-client compat hack from #3066. That override becomes a
    `@model_serializer` in v2, so this fixture is what proves the hack survived.
    """
    return Fleet(
        id=_ID,
        name="test-fleet",
        project_name="test-project",
        spec=fleet_spec(),
        created_at=_CREATED_AT,
        status=FleetStatus.ACTIVE,
        instances=[
            Instance(
                id=_ID,
                project_name="test-project",
                name="test-instance",
                instance_num=0,
                status=InstanceStatus.IDLE,
                created=_CREATED_AT,
                backend=BackendType.AWS,
                region="us-east-1",
            )
        ],
    )


def run_plan() -> RunPlan:
    """
    The single richest response tree — 67 of the 129 model classes reachable from any response
    model are reachable only through here.
    """
    return RunPlan(
        project_name="test-project",
        user="test-user",
        run_spec=run_spec(),
        job_plans=[
            JobPlan(
                job_spec=job_spec(),
                offers=[get_instance_offer_with_availability()],
                total_offers=1,
                max_price=10.5,
            )
        ],
        current_resource=None,
        action=ApplyAction.CREATE,
    )


def fleet_plan() -> FleetPlan:
    return FleetPlan(
        project_name="test-project",
        user="test-user",
        spec=fleet_spec(),
        effective_spec=None,
        current_resource=None,
        offers=[get_instance_offer_with_availability()],
        total_offers=1,
        max_offer_price=10.5,
        action=ApplyAction.CREATE,
    )


def project() -> Project:
    return Project(
        project_id=_ID,
        project_name="test-project",
        owner=user(),
        backends=[],
        members=[
            Member(
                user=user(),
                project_role=ProjectRole.ADMIN,
                permissions=MemberPermissions(can_manage_ssh_fleets=True),
            )
        ],
        is_public=False,
    )


def user() -> User:
    return User(
        id=_ID,
        username="test-user",
        created_at=_CREATED_AT,
        global_role=GlobalRole.USER,
        email=None,
        active=True,
        permissions=UserPermissions(can_create_projects=True),
    )


def user_with_creds() -> UserWithCreds:
    """
    The `SerializeAsAny` case. v2 drops `creds`/`ssh_private_key` from any `User`-typed field, and
    that drop is desired — so this fixture pins that the *top-level* response still carries them.
    """
    return UserWithCreds(
        id=_ID,
        username="test-user",
        created_at=_CREATED_AT,
        global_role=GlobalRole.USER,
        email=None,
        active=True,
        permissions=UserPermissions(can_create_projects=True),
        creds=UserTokenCreds(token="test-token"),
    )


def volume() -> Volume:
    return get_volume(
        id_=_ID,
        name="test-volume",
        project_name="test-project",
        created_at=_CREATED_AT,
        last_processed_at=_CREATED_AT,
    )


def gateway() -> Gateway:
    return Gateway(
        id=_ID,
        name="test-gateway",
        project_name="test-project",
        backend=BackendType.AWS,
        region="us-east-1",
        created_at=_CREATED_AT,
        status=GatewayStatus.RUNNING,
        status_message=None,
        hostname="gateway.example.com",
        wildcard_domain=None,
        default=True,
        replicas=[],
        configuration=gateway_configuration(),
    )


def secret() -> Secret:
    return Secret(id=_ID, name="test-secret", value=None)


def server_info() -> ServerInfo:
    return ServerInfo(server_version="0.20.0")


# --- API request bodies --------------------------------------------------------------
# Serialized by the API client as `body=X.json()`. Picked by the same greedy cover as the
# responses, over the 75 client->server schemas: these six reach 98 of the 171 nested model
# classes. Coverage plateaus there because most of the remainder are wrappers like
# `{names: list[str]}` whose only contribution is their own class, which a fixture pins no
# better than the annotation does.


def apply_fleet_plan_request() -> ApplyFleetPlanRequest:
    """
    Chosen over a simpler request body because it carries a whole `FleetSpec`, so it covers the
    client side of the #3066 `target`-dropping hack too.
    """
    return ApplyFleetPlanRequest(
        plan=ApplyFleetPlanInput(spec=fleet_spec(), current_resource=None),
        force=False,
    )


def apply_run_plan_request() -> ApplyRunPlanRequest:
    """The largest client-sent body: it carries a whole `RunSpec`."""
    return ApplyRunPlanRequest(
        plan=ApplyRunPlanInput(run_spec=run_spec(), current_resource=None),
        force=False,
    )


def apply_gateway_plan_request() -> ApplyGatewayPlanRequest:
    return ApplyGatewayPlanRequest(
        plan=ApplyGatewayPlanInput(
            spec=GatewaySpec(
                configuration=gateway_configuration(),
                configuration_path="gateway.dstack.yml",
            ),
            current_resource=None,
        ),
        force=False,
    )


def create_volume_request() -> CreateVolumeRequest:
    return CreateVolumeRequest(configuration=get_volume_configuration())


def save_repo_creds_request() -> SaveRepoCredsRequest:
    return SaveRepoCredsRequest(
        repo_id="test-repo",
        repo_info=RemoteRepoInfo(repo_name="dstack"),
        repo_creds=RemoteRepoCreds(
            clone_url="https://github.com/dstackai/dstack.git",
            oauth_token="test-token",
        ),
    )


def delete_fleets_request() -> DeleteFleetsRequest:
    return DeleteFleetsRequest(names=["fleet-a", "fleet-b"])


# --- Runner API ------------------------------------------------------------------------
# The server<->runner (shim) protocol. The server is the client here, so `serialization` holds
# the bodies it sends and `parsing` holds the responses it reads back. Unlike the public API
# there is no negotiation on this boundary: a server talks to whatever runner version is baked
# into the running instance's image, so both directions have to stay compatible.


def run() -> Run:
    return Run(
        id=_ID,
        project_name="test-project",
        user="test-user",
        submitted_at=_CREATED_AT,
        last_processed_at=_CREATED_AT,
        status=RunStatus.SUBMITTED,
        run_spec=run_spec(),
        jobs=[Job(job_spec=job_spec(), job_submissions=[job_submission()])],
    )


def job_submission() -> JobSubmission:
    return JobSubmission(
        id=_ID,
        submission_num=0,
        submitted_at=_CREATED_AT,
        last_processed_at=_CREATED_AT,
        status=JobStatus.SUBMITTED,
        job_provisioning_data=job_provisioning_data(),
        job_runtime_data=job_runtime_data(),
    )


def submit_body() -> SubmitBody:
    """The largest body on any boundary — it carries a whole `Run` plus the job spec."""
    return SubmitBody(
        run=run(),
        job_spec=job_spec(),
        job_submission=job_submission(),
        run_spec=run_spec(),
    )


def healthcheck_response() -> HealthcheckResponse:
    return HealthcheckResponse(service="dstack-shim", version="0.20.0")


# No `PullResponse` factory: `LogEvent.message` is `bytes`, which the project's orjson dumper
# refuses outright, so the model has no working `.json()` at all. Harmless today because the
# server only ever parses it (`services/runner/client.py`), but it means that write path has
# never run — worth knowing before the serializer is swapped.


def task_submit_request() -> TaskSubmitRequest:
    """The newer per-task API; `TaskSubmitRequest` and `SubmitBody` are separate protocols."""
    return TaskSubmitRequest(
        id=str(_ID),
        name="test-task",
        registry_username="",
        registry_password="",
        image_name="dstackai/base:latest",
        container_user="root",
        privileged=False,
        gpu=1,
        cpu=2.0,
        memory=16 * 1024**3,
        shm_size=1024**3,
        network_mode=NetworkMode.HOST,
        volumes=[],
        volume_mounts=[],
        instance_mounts=[],
        gpu_devices=[],
        host_ssh_user="ubuntu",
        host_ssh_keys=["ssh-rsa HOST"],
        container_ssh_keys=["ssh-rsa CONTAINER"],
    )


def legacy_submit_body() -> LegacySubmitBody:
    """Kept because old runners are still in the wild; its shape must not drift either."""
    return LegacySubmitBody(
        username="",
        password="",
        image_name="dstackai/base:latest",
        privileged=False,
        container_name="test-container",
        container_user="root",
        shm_size=1024**3,
        public_keys=["ssh-rsa PUBLIC"],
        ssh_user="ubuntu",
        ssh_key="ssh-rsa SSH",
        mounts=[],
        volumes=[],
        instance_mounts=[],
    )


def shutdown_request() -> ShutdownRequest:
    return ShutdownRequest(force=True)


def component_install_request() -> ComponentInstallRequest:
    return ComponentInstallRequest(name=ComponentName.SHIM, url="https://example.com/shim.tar.gz")


def task_terminate_request() -> TaskTerminateRequest:
    return TaskTerminateRequest(
        termination_reason="MAX_DURATION_EXCEEDED",
        termination_message="max duration exceeded",
        timeout=10,
    )


def job_info_response() -> JobInfoResponse:
    return JobInfoResponse(working_dir="/workflow", username="ubuntu")


def task_info_response() -> TaskInfoResponse:
    return TaskInfoResponse(
        id=str(_ID),
        status=TaskStatus.RUNNING,
        termination_reason="",
        termination_message="",
    )


def instance_health_response() -> InstanceHealthResponse:
    """All fields optional; the empty shape is what a runner without DCGM reports."""
    return InstanceHealthResponse()


# --- Gateway API -----------------------------------------------------------------------
# The server<->gateway protocol. Note the server builds these payloads as hand-written dicts
# rather than dumping a model (see `services/gateways/client.py`), so only the gateway's own
# parsing side is model-driven — hence the request shapes live in `parsing/gateway` with
# hand-written inputs, and only the stats response is serialized from a model here.
#
# These schemas are plain `BaseModel`, not `CoreModel`: they already default to extra="ignore"
# in both pydantic versions, so they need neither the duality shim nor a strictness test.


def service_stats() -> ServiceStats:
    return ServiceStats(
        project_name="test-project",
        run_name="test-run",
        stats={60: Stat(requests=10, request_time=0.125)},
    )


# --- Model proxy ---------------------------------------------------------------------------
# The OpenAI-compatible proxy. Both directions are model-driven: a request is parsed from the
# caller and then forwarded upstream, and the upstream's reply is parsed back.
#
# The forward leg is the only place in the codebase that dumps with `exclude_unset=True`
# (`proxy/lib/services/model_proxy/clients/openai.py`), which makes `__fields_set__` load-bearing
# here and nowhere else: if a field the caller never set starts counting as set, the proxy begins
# sending keys the caller did not ask for, and the upstream model behaves differently.


def chat_completions_request() -> ChatCompletionsRequest:
    """Only some fields set on purpose — `exclude_unset` is the point."""
    return ChatCompletionsRequest(
        model="llama",
        messages=[ChatMessage(role="user", content="hi")],
        temperature=0.7,
        stop=["\n"],
    )


def register_entrypoint_request() -> RegisterEntrypointRequest:
    return RegisterEntrypointRequest(domain="gateway.example.com", https=True)


# --- Model proxy responses -------------------------------------------------------------------
# Returned to the caller of the OpenAI-compatible API. `ChatCompletionsChunk` is serialized one
# chunk at a time into an SSE stream (`proxy/lib/routers/model_proxy.py`), which is a fifth dump
# path: `f"data:{chunk.json()}"` rather than a response body.


def models_response() -> ModelsResponse:
    return ModelsResponse(
        data=[Model(object="model", id="llama", created=1700000000, owned_by="dstack")]
    )


def chat_completions_chunk() -> ChatCompletionsChunk:
    return ChatCompletionsChunk(
        id="chatcmpl-1",
        choices=[
            ChatCompletionsChunkChoice(
                delta={"role": "assistant", "content": "hi"}, index=0, finish_reason=None
            )
        ],
        created=1700000000,
        model="llama",
        system_fingerprint="fp_1",
    )
