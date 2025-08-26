import logging
import time
from collections import defaultdict
from collections.abc import Container as ContainerT
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from tempfile import NamedTemporaryFile
from typing import Optional

from nebius.aio.authorization.options import options_to_metadata
from nebius.aio.operation import Operation as SDKOperation
from nebius.aio.service_error import RequestError, StatusCode
from nebius.aio.token.renewable import OPTION_RENEW_REQUEST_TIMEOUT, OPTION_RENEW_SYNCHRONOUS
from nebius.api.nebius.common.v1 import Operation, ResourceMetadata
from nebius.api.nebius.compute.v1 import (
    AttachedDiskSpec,
    CreateDiskRequest,
    CreateGpuClusterRequest,
    CreateInstanceRequest,
    DeleteDiskRequest,
    DeleteGpuClusterRequest,
    DeleteInstanceRequest,
    DiskServiceClient,
    DiskSpec,
    ExistingDisk,
    GetInstanceRequest,
    GpuClusterServiceClient,
    GpuClusterSpec,
    Instance,
    InstanceGpuClusterSpec,
    InstanceRecoveryPolicy,
    InstanceServiceClient,
    InstanceSpec,
    IPAddress,
    NetworkInterfaceSpec,
    PreemptibleSpec,
    PublicIPAddress,
    ResourcesSpec,
    SourceImageFamily,
)
from nebius.api.nebius.iam.v1 import (
    Container,
    ListProjectsRequest,
    ListTenantsRequest,
    ProjectServiceClient,
    TenantServiceClient,
)
from nebius.api.nebius.vpc.v1 import ListSubnetsRequest, Subnet, SubnetServiceClient
from nebius.sdk import SDK

from dstack._internal.core.backends.base.configurator import raise_invalid_credentials_error
from dstack._internal.core.backends.nebius.models import (
    DEFAULT_PROJECT_NAME_PREFIX,
    NebiusServiceAccountCreds,
)
from dstack._internal.core.errors import BackendError, NoCapacityError
from dstack._internal.utils.event_loop import DaemonEventLoop
from dstack._internal.utils.logging import get_logger

#
# Guidelines on using the Nebius SDK:
#
# Do not use Request.wait() or other sync SDK methods, they suffer from deadlocks.
# Instead, use async methods and await them with LOOP.await_()
LOOP = DaemonEventLoop()
# Pass a timeout to all methods to avoid infinite waiting
REQUEST_TIMEOUT = 10
# Pass REQUEST_MD to all methods to avoid infinite retries in case of invalid credentials
REQUEST_MD = options_to_metadata(
    {
        OPTION_RENEW_SYNCHRONOUS: "true",
        OPTION_RENEW_REQUEST_TIMEOUT: "5",
    }
)

# disables log messages about errors such as invalid creds or expired timeouts
logging.getLogger("nebius").setLevel(logging.CRITICAL)
logger = get_logger(__name__)


@contextmanager
def wrap_capacity_errors() -> Generator[None, None, None]:
    try:
        yield
    except RequestError as e:
        if e.status.code == StatusCode.RESOURCE_EXHAUSTED or "Quota limit exceeded" in str(e):
            raise NoCapacityError(e)
        raise


@contextmanager
def ignore_errors(status_codes: ContainerT[StatusCode]) -> Generator[None, None, None]:
    try:
        yield
    except RequestError as e:
        if e.status.code not in status_codes:
            raise


def make_sdk(creds: NebiusServiceAccountCreds) -> SDK:
    with NamedTemporaryFile("w") as f:
        f.write(creds.private_key_content)
        f.flush()
        return SDK(
            service_account_private_key_file_name=f.name,
            service_account_public_key_id=creds.public_key_id,
            service_account_id=creds.service_account_id,
        )


def wait_for_operation(
    op: SDKOperation[Operation],
    timeout: float,
    interval: float = 1,
) -> None:
    # Re-implementation of SDKOperation.wait() to avoid https://github.com/nebius/pysdk/issues/74
    deadline = time.monotonic() + timeout
    while not op.done():
        if time.monotonic() + interval > deadline:
            raise TimeoutError(f"Operation {op.id} wait timeout")
        time.sleep(interval)
        LOOP.await_(op.update(per_retry_timeout=REQUEST_TIMEOUT, metadata=REQUEST_MD))


def get_region_to_project_id_map(
    sdk: SDK, configured_regions: Optional[list[str]], configured_project_ids: Optional[list[str]]
) -> dict[str, str]:
    """Validate backend settings and build region->project_id map"""

    projects = list_tenant_projects(sdk)
    if configured_regions:
        validate_regions(
            configured=set(configured_regions), available={p.status.region for p in projects}
        )
    if configured_project_ids is not None:
        return _get_region_to_configured_project_id_map(
            projects, configured_project_ids, configured_regions
        )
    else:
        return _get_region_to_default_project_id_map(projects, configured_regions)


def validate_regions(configured: set[str], available: set[str]) -> None:
    if invalid := set(configured) - available:
        raise_invalid_credentials_error(
            fields=[["regions"]],
            details=(
                f"Configured regions {invalid} do not exist in this Nebius tenancy."
                " Omit `regions` to use all regions or select some of the available regions:"
                f" {available}"
            ),
        )


def list_tenant_projects(sdk: SDK) -> Sequence[Container]:
    tenants = LOOP.await_(
        TenantServiceClient(sdk).list(
            ListTenantsRequest(), per_retry_timeout=REQUEST_TIMEOUT, metadata=REQUEST_MD
        )
    )
    if len(tenants.items) != 1:
        raise ValueError(f"Expected to find 1 tenant, found {(len(tenants.items))}")
    tenant_id = tenants.items[0].metadata.id
    projects = LOOP.await_(
        ProjectServiceClient(sdk).list(
            ListProjectsRequest(parent_id=tenant_id, page_size=999),
            per_retry_timeout=REQUEST_TIMEOUT,
            metadata=REQUEST_MD,
        )
    )
    return projects.items


def _get_region_to_default_project_id_map(
    all_tenant_projects: Iterable[Container], configured_regions: Optional[list[str]]
) -> dict[str, str]:
    region_to_projects: defaultdict[str, list[Container]] = defaultdict(list)
    for project in all_tenant_projects:
        region_to_projects[project.status.region].append(project)
    region_to_project_id = {}
    for region, region_projects in region_to_projects.items():
        if configured_regions and region not in configured_regions:
            continue
        if len(region_projects) != 1:
            region_projects = [
                p
                for p in region_projects
                if p.metadata.name.startswith(DEFAULT_PROJECT_NAME_PREFIX)
            ]
            if len(region_projects) != 1:
                raise_invalid_credentials_error(
                    ["regions"],
                    (
                        f"Could not find the default project in region {region}."
                        " Consider setting the `projects` property in backend settings"
                    ),
                )
        region_to_project_id[region] = region_projects[0].metadata.id
    return region_to_project_id


def _get_region_to_configured_project_id_map(
    all_tenant_projects: Iterable[Container],
    configured_project_ids: list[str],
    configured_regions: Optional[list[str]],
) -> dict[str, str]:
    project_id_to_project = {p.metadata.id: p for p in all_tenant_projects}
    region_to_project_id = {}
    for project_id in configured_project_ids:
        project = project_id_to_project.get(project_id)
        if project is None:
            raise_invalid_credentials_error(
                ["projects"],
                f"Configured project ID {project_id!r} not found in this Nebius tenancy",
            )
        duplicate_project_id = region_to_project_id.get(project.status.region)
        if duplicate_project_id:
            raise_invalid_credentials_error(
                ["projects"],
                (
                    f"Configured projects {project_id} and {duplicate_project_id}"
                    f" both belong to the same region {project.status.region}."
                    " Only one project per region is allowed"
                ),
            )
        region_to_project_id[project.status.region] = project_id
    if configured_regions:
        # only filter by region after validating all project IDs
        return {
            region: project_id
            for region, project_id in region_to_project_id.items()
            if region in configured_regions
        }
    return region_to_project_id


def get_default_subnet(sdk: SDK, project_id: str) -> Subnet:
    subnets = LOOP.await_(
        SubnetServiceClient(sdk).list(
            ListSubnetsRequest(parent_id=project_id, page_size=999),
            per_retry_timeout=REQUEST_TIMEOUT,
            metadata=REQUEST_MD,
        )
    )
    for subnet in subnets.items:
        if subnet.metadata.name.startswith("default-subnet"):
            return subnet
    raise BackendError(f"Could not find default subnet in project {project_id}")


def create_disk(
    sdk: SDK, name: str, project_id: str, size_mib: int, image_family: str
) -> SDKOperation[Operation]:
    client = DiskServiceClient(sdk)
    request = CreateDiskRequest(
        metadata=ResourceMetadata(
            name=name,
            parent_id=project_id,
        ),
        spec=DiskSpec(
            size_mebibytes=size_mib,
            type=DiskSpec.DiskType.NETWORK_SSD,
            source_image_family=SourceImageFamily(image_family=image_family),
        ),
    )
    with wrap_capacity_errors():
        return LOOP.await_(
            client.create(request, per_retry_timeout=REQUEST_TIMEOUT, metadata=REQUEST_MD)
        )


def delete_disk(sdk: SDK, disk_id: str) -> None:
    LOOP.await_(
        DiskServiceClient(sdk).delete(
            DeleteDiskRequest(id=disk_id), per_retry_timeout=REQUEST_TIMEOUT, metadata=REQUEST_MD
        )
    )


def create_instance(
    sdk: SDK,
    name: str,
    project_id: str,
    user_data: str,
    platform: str,
    preset: str,
    cluster_id: Optional[str],
    disk_id: str,
    subnet_id: str,
    preemptible: bool,
) -> SDKOperation[Operation]:
    client = InstanceServiceClient(sdk)
    request = CreateInstanceRequest(
        metadata=ResourceMetadata(
            name=name,
            parent_id=project_id,
        ),
        spec=InstanceSpec(
            cloud_init_user_data=user_data,
            resources=ResourcesSpec(platform=platform, preset=preset),
            gpu_cluster=InstanceGpuClusterSpec(id=cluster_id) if cluster_id is not None else None,
            boot_disk=AttachedDiskSpec(
                attach_mode=AttachedDiskSpec.AttachMode.READ_WRITE,
                existing_disk=ExistingDisk(id=disk_id),
            ),
            network_interfaces=[
                NetworkInterfaceSpec(
                    name="dstack-default-interface",
                    subnet_id=subnet_id,
                    ip_address=IPAddress(),
                    public_ip_address=PublicIPAddress(static=True),
                )
            ],
            preemptible=PreemptibleSpec(
                priority=1, on_preemption=PreemptibleSpec.PreemptionPolicy.STOP
            )
            if preemptible
            else None,
            recovery_policy=InstanceRecoveryPolicy.FAIL if preemptible else None,
        ),
    )
    with wrap_capacity_errors():
        return LOOP.await_(
            client.create(request, per_retry_timeout=REQUEST_TIMEOUT, metadata=REQUEST_MD)
        )


def get_instance(sdk: SDK, instance_id: str) -> Instance:
    return LOOP.await_(
        InstanceServiceClient(sdk).get(
            GetInstanceRequest(id=instance_id),
            per_retry_timeout=REQUEST_TIMEOUT,
            metadata=REQUEST_MD,
        )
    )


def delete_instance(sdk: SDK, instance_id: str) -> SDKOperation[Operation]:
    return LOOP.await_(
        InstanceServiceClient(sdk).delete(
            DeleteInstanceRequest(id=instance_id),
            per_retry_timeout=REQUEST_TIMEOUT,
            metadata=REQUEST_MD,
        )
    )


def create_cluster(sdk: SDK, name: str, project_id: str, fabric: str) -> SDKOperation[Operation]:
    with wrap_capacity_errors():
        return LOOP.await_(
            GpuClusterServiceClient(sdk).create(
                CreateGpuClusterRequest(
                    metadata=ResourceMetadata(name=name, parent_id=project_id),
                    spec=GpuClusterSpec(infiniband_fabric=fabric),
                ),
                per_retry_timeout=REQUEST_TIMEOUT,
                metadata=REQUEST_MD,
            )
        )


def delete_cluster(sdk: SDK, cluster_id: str) -> None:
    return LOOP.await_(
        GpuClusterServiceClient(sdk).delete(
            DeleteGpuClusterRequest(id=cluster_id),
            per_retry_timeout=REQUEST_TIMEOUT,
            metadata=REQUEST_MD,
        )
    )
