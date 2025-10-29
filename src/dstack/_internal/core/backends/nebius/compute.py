import json
import random
import shlex
import time
from collections.abc import Iterable
from functools import cached_property
from typing import List, Optional

from nebius.aio.operation import Operation as SDKOperation
from nebius.aio.service_error import RequestError, StatusCode
from nebius.api.nebius.common.v1 import Operation
from nebius.sdk import SDK

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithPrivilegedSupport,
    generate_unique_instance_name,
    get_user_data,
    merge_tags,
)
from dstack._internal.core.backends.base.offers import (
    OfferModifier,
    get_catalog_offers,
    get_offers_disk_modifier,
)
from dstack._internal.core.backends.nebius import resources
from dstack._internal.core.backends.nebius.models import (
    NebiusConfig,
    NebiusOfferBackendData,
    NebiusServiceAccountCreds,
)
from dstack._internal.core.errors import (
    BackendError,
    NotYetTerminated,
    ProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import (
    PlacementGroup,
    PlacementGroupProvisioningData,
    PlacementStrategy,
)
from dstack._internal.core.models.resources import Memory, Range
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
CONFIGURABLE_DISK_SIZE = Range[Memory](
    min=Memory.parse("40GB"),  # min for the ubuntu22.04-cuda12 image
    max=Memory.parse("8192GB"),  # max for the NETWORK_SSD disk type
)
WAIT_FOR_DISK_TIMEOUT = 20
WAIT_FOR_INSTANCE_TIMEOUT = 30
WAIT_FOR_INSTANCE_UPDATE_INTERVAL = 2.5
DELETE_INSTANCE_TIMEOUT = 25
DOCKER_DAEMON_CONFIG = {
    "runtimes": {"nvidia": {"args": [], "path": "nvidia-container-runtime"}},
    # Workaround for https://github.com/NVIDIA/nvidia-container-toolkit/issues/48
    "exec-opts": ["native.cgroupdriver=cgroupfs"],
}
SETUP_COMMANDS = [
    'sed -i "s/.*AllowTcpForwarding.*/AllowTcpForwarding yes/g" /etc/ssh/sshd_config',
    "service ssh restart",
    f"echo {shlex.quote(json.dumps(DOCKER_DAEMON_CONFIG))} > /etc/docker/daemon.json",
    "service docker restart",
]
SUPPORTED_PLATFORMS = [
    "gpu-h100-sxm",
    "gpu-h200-sxm",
    "gpu-b200-sxm",
    "gpu-l40s-a",
    "gpu-l40s-d",
    "cpu-d3",
    "cpu-e2",
]


class NebiusCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    Compute,
):
    def __init__(self, config: NebiusConfig):
        super().__init__()
        self.config = config
        self._subnet_id_cache: dict[str, str] = {}

    @cached_property
    def _sdk(self) -> SDK:
        assert isinstance(self.config.creds, NebiusServiceAccountCreds)
        return resources.make_sdk(self.config.creds)

    @cached_property
    def _region_to_project_id(self) -> dict[str, str]:
        return resources.get_region_to_project_id_map(
            self._sdk,
            configured_regions=self.config.regions,
            configured_project_ids=self.config.projects,
        )

    def _get_subnet_id(self, region: str) -> str:
        if region not in self._subnet_id_cache:
            self._subnet_id_cache[region] = resources.get_default_subnet(
                self._sdk, self._region_to_project_id[region]
            ).metadata.id
        return self._subnet_id_cache[region]

    def get_all_offers_with_availability(self) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.NEBIUS,
            locations=list(self._region_to_project_id),
            extra_filter=_supported_instances,
        )
        return [
            InstanceOfferWithAvailability(
                **offer.dict(),
                availability=InstanceAvailability.UNKNOWN,
            )
            for offer in offers
        ]

    def get_offers_modifiers(self, requirements: Requirements) -> Iterable[OfferModifier]:
        return [get_offers_disk_modifier(CONFIGURABLE_DISK_SIZE, requirements)]

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        # NOTE: This method can block for a long time as it waits for the boot disk to be created
        # and the instance to enter the STARTING state. This has to be done in create_instance so
        # that we can handle quota and availability errors that may occur even after creating an
        # instance.
        instance_name = generate_unique_instance_name(instance_config)
        platform, preset = instance_offer.instance.name.split()
        cluster_id = None
        if placement_group:
            assert placement_group.provisioning_data is not None
            backend_data = NebiusPlacementGroupBackendData.load(
                placement_group.provisioning_data.backend_data
            )
            if backend_data.cluster is not None:
                cluster_id = backend_data.cluster.id

        labels = {
            "owner": "dstack",
            "dstack_project": instance_config.project_name.lower(),
            "dstack_name": instance_config.instance_name,
            "dstack_user": instance_config.user.lower(),
        }
        labels = merge_tags(
            base_tags=labels,
            backend_tags=self.config.tags,
            resource_tags=instance_config.tags,
        )
        labels = resources.filter_invalid_labels(labels)
        gpus = instance_offer.instance.resources.gpus
        create_disk_op = resources.create_disk(
            sdk=self._sdk,
            name=instance_name,
            project_id=self._region_to_project_id[instance_offer.region],
            size_mib=instance_offer.instance.resources.disk.size_mib,
            image_family="ubuntu24.04-cuda12"
            if gpus and gpus[0].name == "B200"
            else "ubuntu22.04-cuda12",
            labels=labels,
        )
        create_instance_op = None
        try:
            logger.debug("Blocking until disk %s is created", create_disk_op.resource_id)
            resources.wait_for_operation(create_disk_op, timeout=WAIT_FOR_DISK_TIMEOUT)
            if not create_disk_op.successful():
                raw_op = create_disk_op.raw()
                raise ProvisioningError(
                    f"Create disk operation failed. Message: {raw_op.status.message}."
                    f" Details: {raw_op.status.details}"
                )
            create_instance_op = resources.create_instance(
                sdk=self._sdk,
                name=instance_name,
                project_id=self._region_to_project_id[instance_offer.region],
                user_data=get_user_data(
                    instance_config.get_public_keys(),
                    backend_specific_commands=SETUP_COMMANDS,
                ),
                platform=platform,
                preset=preset,
                cluster_id=cluster_id,
                disk_id=create_disk_op.resource_id,
                subnet_id=self._get_subnet_id(instance_offer.region),
                preemptible=instance_offer.instance.resources.spot,
                labels=labels,
            )
            _wait_for_instance(self._sdk, create_instance_op)
        except BaseException:
            if create_instance_op is not None:
                try:
                    with resources.ignore_errors([StatusCode.NOT_FOUND]):
                        delete_instance_op = resources.delete_instance(
                            self._sdk, create_instance_op.resource_id
                        )
                    resources.wait_for_operation(
                        delete_instance_op, timeout=DELETE_INSTANCE_TIMEOUT
                    )
                except Exception as e:
                    logger.exception(
                        "Could not delete instance %s: %s", create_instance_op.resource_id, e
                    )
            try:
                with resources.ignore_errors([StatusCode.NOT_FOUND]):
                    resources.delete_disk(self._sdk, create_disk_op.resource_id)
            except Exception as e:
                logger.exception(
                    "Could not delete boot disk %s: %s", create_disk_op.resource_id, e
                )
            raise
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=create_instance_op.resource_id,
            hostname=None,
            region=instance_offer.region,
            price=instance_offer.price,
            ssh_port=22,
            username="ubuntu",
            dockerized=True,
            backend_data=NebiusInstanceBackendData(boot_disk_id=create_disk_op.resource_id).json(),
        )

    def update_provisioning_data(
        self, provisioning_data, project_ssh_public_key, project_ssh_private_key
    ):
        instance = resources.get_instance(self._sdk, provisioning_data.instance_id)
        if not instance.status.network_interfaces:
            return
        interface = instance.status.network_interfaces[0]
        provisioning_data.hostname, _ = interface.public_ip_address.address.split("/")
        provisioning_data.internal_ip, _ = interface.ip_address.address.split("/")

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        backend_data_parsed = NebiusInstanceBackendData.load(backend_data)
        try:
            instance = resources.get_instance(self._sdk, instance_id)
        except RequestError as e:
            if e.status.code != StatusCode.NOT_FOUND:
                raise
            instance = None
        if instance is not None:
            if instance.status.state != instance.status.InstanceState.DELETING:
                resources.delete_instance(self._sdk, instance_id)
                raise NotYetTerminated(
                    "Requested instance deletion."
                    " Will wait for deletion before deleting the boot disk."
                    f" Instance state was: {instance.status.state.name}"
                )
            else:
                raise NotYetTerminated(
                    "Waiting for instance deletion before deleting the boot disk."
                    f" Instance state: {instance.status.state.name}"
                )
        with resources.ignore_errors([StatusCode.NOT_FOUND]):
            resources.delete_disk(self._sdk, backend_data_parsed.boot_disk_id)

    def create_placement_group(
        self,
        placement_group: PlacementGroup,
        master_instance_offer: InstanceOffer,
    ) -> PlacementGroupProvisioningData:
        assert placement_group.configuration.placement_strategy == PlacementStrategy.CLUSTER
        master_instance_offer_backend_data: NebiusOfferBackendData = (
            NebiusOfferBackendData.__response__.parse_obj(master_instance_offer.backend_data)
        )
        fabrics = list(master_instance_offer_backend_data.fabrics)
        if self.config.fabrics is not None:
            fabrics = [f for f in fabrics if f in self.config.fabrics]
        placement_group_backend_data = NebiusPlacementGroupBackendData(cluster=None)
        # Only create a Nebius cluster if the instance supports it.
        # For other instances, return dummy PlacementGroupProvisioningData.
        if fabrics:
            fabric = random.choice(fabrics)
            op = resources.create_cluster(
                self._sdk,
                name=placement_group.name,
                project_id=self._region_to_project_id[placement_group.configuration.region],
                fabric=fabric,
            )
            placement_group_backend_data.cluster = NebiusClusterBackendData(
                id=op.resource_id,
                fabric=fabric,
            )
        return PlacementGroupProvisioningData(
            backend=BackendType.NEBIUS,
            backend_data=placement_group_backend_data.json(),
        )

    def delete_placement_group(self, placement_group: PlacementGroup) -> None:
        assert placement_group.provisioning_data is not None
        backend_data = NebiusPlacementGroupBackendData.load(
            placement_group.provisioning_data.backend_data
        )
        if backend_data.cluster is not None:
            with resources.ignore_errors([StatusCode.NOT_FOUND]):
                resources.delete_cluster(self._sdk, backend_data.cluster.id)

    def is_suitable_placement_group(
        self,
        placement_group: PlacementGroup,
        instance_offer: InstanceOffer,
    ) -> bool:
        if placement_group.configuration.region != instance_offer.region:
            return False
        assert placement_group.provisioning_data is not None
        placement_group_backend_data = NebiusPlacementGroupBackendData.load(
            placement_group.provisioning_data.backend_data
        )
        instance_offer_backend_data: NebiusOfferBackendData = (
            NebiusOfferBackendData.__response__.parse_obj(instance_offer.backend_data)
        )
        return (
            placement_group_backend_data.cluster is None
            or placement_group_backend_data.cluster.fabric in instance_offer_backend_data.fabrics
        )


class NebiusInstanceBackendData(CoreModel):
    boot_disk_id: str

    @classmethod
    def load(cls, raw: Optional[str]) -> "NebiusInstanceBackendData":
        assert raw is not None
        return cls.__response__.parse_raw(raw)


class NebiusClusterBackendData(CoreModel):
    id: str
    fabric: str


class NebiusPlacementGroupBackendData(CoreModel):
    cluster: Optional[NebiusClusterBackendData]

    @classmethod
    def load(cls, raw: Optional[str]) -> "NebiusPlacementGroupBackendData":
        assert raw is not None
        return cls.__response__.parse_raw(raw)


def _wait_for_instance(sdk: SDK, op: SDKOperation[Operation]) -> None:
    start = time.monotonic()
    while True:
        if op.done() and not op.successful():
            raise ProvisioningError(
                f"Create instance operation failed. Message: {op.raw().status.message}."
                f" Details: {op.raw().status.details}"
            )
        instance = resources.get_instance(sdk, op.resource_id)
        if instance.status.state in [
            instance.status.InstanceState.STARTING,
            instance.status.InstanceState.RUNNING,
        ]:
            break
        if time.monotonic() - start > WAIT_FOR_INSTANCE_TIMEOUT:
            raise BackendError(
                f"Instance {instance.metadata.id} did not start booting in time."
                f" Status: {instance.status.state.name}"
            )
        logger.debug(
            "Waiting for instance %s. Status: %s. Operation status: %s",
            instance.metadata.name,
            instance.status.state.name,
            op.status(),
        )
        time.sleep(WAIT_FOR_INSTANCE_UPDATE_INTERVAL)
        resources.LOOP.await_(
            op.update(
                per_retry_timeout=resources.REQUEST_TIMEOUT,
                auth_options=resources.REQUEST_AUTH_OPTIONS,
            )
        )


def _supported_instances(offer: InstanceOffer) -> bool:
    platform, _ = offer.instance.name.split()
    return platform in SUPPORTED_PLATFORMS
