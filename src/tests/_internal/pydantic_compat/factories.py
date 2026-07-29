"""
Deterministic model instances for the comparison fixtures.

Every value is pinned — no `uuid4()`, no `now()` — so a fixture only changes when serialization
changes. Builds on `dstack._internal.server.testing.common` where a factory already exists, so
these stay in sync with the shapes the rest of the suite uses.
"""

import uuid
from datetime import datetime, timezone

from dstack._internal.core.backends.aws.models import AWSCreds
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.compute_groups import ComputeGroupProvisioningData
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.fleets import Fleet, FleetPlan, FleetSpec, FleetStatus
from dstack._internal.core.models.gateways import (
    Gateway,
    GatewayComputeConfiguration,
    GatewayConfiguration,
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
)
from dstack._internal.core.models.placement import (
    PlacementGroupConfiguration,
    PlacementGroupProvisioningData,
)
from dstack._internal.core.models.profiles import (
    Profile,
    ProfileRetry,
    RetryEvent,
    SpotPolicy,
)
from dstack._internal.core.models.projects import (
    Member,
    MemberPermissions,
    Project,
    ProjectRole,
)
from dstack._internal.core.models.resources import (
    ComputeCapability,
    GPUSpec,
    Memory,
    Range,
    ResourcesSpec,
)
from dstack._internal.core.models.runs import (
    ImagePullProgress,
    JobPlan,
    JobProvisioningData,
    JobRuntimeData,
    JobSpec,
    Requirements,
    RunPlan,
    RunSpec,
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
from dstack._internal.server.schemas.fleets import (
    ApplyFleetPlanInput,
    ApplyFleetPlanRequest,
    DeleteFleetsRequest,
)
from dstack._internal.server.testing.common import (
    get_compute_group_provisioning_data,
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
# Written to a `Text` column with `.json()`. Rows outlive any release, so each stored model
# is an independent liability and gets its own fixture rather than standing in for a shared
# shape — unlike the API surfaces below, which are covered by feature instead.


def aws_creds() -> AWSCreds:
    """A custom-root discriminated union, read from `BackendModel.auth`."""
    return AWSCreds.parse_obj({"type": "access_key", "access_key": "AK", "secret_key": "SK"})


def compute_group_provisioning_data() -> ComputeGroupProvisioningData:
    return get_compute_group_provisioning_data()


def fleet_spec() -> FleetSpec:
    return get_fleet_spec()


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
    return get_instance_configuration()


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
        max_duration=7200,
        stop_duration=300,
        idle_duration=600,
        spot_policy=SpotPolicy.AUTO,
        retry=ProfileRetry(on_events=[RetryEvent.NO_CAPACITY], duration=3600),
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
        profile=Profile(name="default", max_duration=7200, idle_duration=300),
        configuration=DevEnvironmentConfiguration(
            ide="vscode",
            resources=ResourcesSpec(
                cpu=Range[int](min=2, max=8),
                memory=Range[Memory](min=Memory(16), max=None),
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
# Returned from a router through `CustomORJSONResponse`.


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
        spec=get_fleet_spec(),
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
        spec=get_fleet_spec(),
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
# Serialized by the API client as `body=X.json()`.


def apply_fleet_plan_request() -> ApplyFleetPlanRequest:
    """
    Chosen over a simpler request body because it carries a whole `FleetSpec`, so it covers the
    client side of the #3066 `target`-dropping hack too.
    """
    return ApplyFleetPlanRequest(
        plan=ApplyFleetPlanInput(spec=get_fleet_spec(), current_resource=None),
        force=False,
    )


def delete_fleets_request() -> DeleteFleetsRequest:
    return DeleteFleetsRequest(names=["fleet-a", "fleet-b"])
