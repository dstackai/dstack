from collections.abc import Iterable
from typing import List, Optional

import gpuhunt
from gpuhunt.providers.crusoe import CrusoeProvider

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithPrivilegedSupport,
    generate_unique_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import (
    OfferModifier,
    get_catalog_offers,
    get_offers_disk_modifier,
)
from dstack._internal.core.backends.crusoe.models import CrusoeConfig
from dstack._internal.core.backends.crusoe.resources import CrusoeClient
from dstack._internal.core.errors import BackendError, NotYetTerminated
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

# Range for the persistent data disk created for instance types without ephemeral NVMe.
CONFIGURABLE_DISK_SIZE = Range[Memory](
    min=Memory.parse("50GB"),
    max=Memory.parse("5000GB"),
)
WAIT_FOR_DISK_TIMEOUT = 30
WAIT_FOR_VM_TIMEOUT = 120

SETUP_COMMANDS = [
    'sed -i "s/.*AllowTcpForwarding.*/AllowTcpForwarding yes/g" /etc/ssh/sshd_config',
    "service ssh restart",
]

# Set up storage on the best available disk and move containerd there.
# Docker on Crusoe images delegates image storage to containerd's native snapshotter,
# so /var/lib/containerd is what determines container disk space.
# Handles: /dev/vdb (persistent data disk we create) or /dev/nvme* (ephemeral NVMe).
# For multiple NVMe drives, uses mdadm RAID-0 for maximum space.
STORAGE_SETUP_COMMANDS = [
    (
        "DISK='' && "
        "if [ -b /dev/vdb ]; then DISK=/dev/vdb; "
        "elif ls /dev/nvme*n1 >/dev/null 2>&1; then"
        " NVME_DEVS=$(ls /dev/nvme*n1 2>/dev/null);"
        " NVME_COUNT=$(echo $NVME_DEVS | wc -w);"
        " if [ $NVME_COUNT -eq 1 ]; then DISK=$NVME_DEVS;"
        " elif [ $NVME_COUNT -gt 1 ]; then"
        "  apt-get install -y -qq mdadm >/dev/null 2>&1 || true;"
        "  mdadm --create /dev/md0 --level=0 --raid-devices=$NVME_COUNT $NVME_DEVS --force --run;"
        "  DISK=/dev/md0;"
        " fi;"
        "fi && "
        'if [ -n "$DISK" ]; then'
        " mkfs.ext4 -q -F $DISK"
        " && mkdir -p /data"
        " && mount $DISK /data"
        " && service docker stop"
        " && systemctl stop containerd || true"
        " && mkdir -p /data/containerd"
        " && rsync -a /var/lib/containerd/ /data/containerd/"
        " && mount --bind /data/containerd /var/lib/containerd"
        " && systemctl start containerd || true"
        " && service docker start"
        "; fi"
    ),
]

IMAGE_SXM_DOCKER = "ubuntu22.04-nvidia-sxm-docker:latest"
IMAGE_PCIE_DOCKER = "ubuntu22.04-nvidia-pcie-docker:latest"
IMAGE_ROCM = "ubuntu-rocm:latest"


def _get_image(instance_name: str, gpu_type: str) -> str:
    # Check instance name for SXM -- gpu_type from gpuhunt is normalized (e.g. "A100")
    # and doesn't contain "SXM", but instance names like "a100-80gb-sxm-ib.8x" do.
    if "-sxm" in instance_name.lower():
        return IMAGE_SXM_DOCKER
    if "MI3" in gpu_type:
        return IMAGE_ROCM
    # Use PCIe docker image for both PCIe GPUs and CPU-only types.
    # Crusoe has no CPU-specific Docker image; the base ubuntu image lacks Docker.
    return IMAGE_PCIE_DOCKER


def _is_ib_type(instance_name: str) -> bool:
    prefix = instance_name.split(".")[0]
    return prefix.endswith("-ib") or prefix.endswith("-roce")


def _get_instance_family(instance_name: str) -> str:
    return instance_name.rsplit(".", 1)[0]


def _has_ephemeral_disk(offer: InstanceOffer) -> bool:
    """Check if the instance type has ephemeral NVMe storage via gpuhunt provider_data."""
    backend_data = offer.backend_data or {}
    return backend_data.get("disk_gb", 0) > 0


class CrusoeCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    Compute,
):
    def __init__(self, config: CrusoeConfig):
        super().__init__()
        self.config = config
        self._client = CrusoeClient(config.creds, config.project_id)
        self._catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self._catalog.add_provider(
            CrusoeProvider(
                access_key=config.creds.access_key,
                secret_key=config.creds.secret_key,
                project_id=config.project_id,
            )
        )

    def get_all_offers_with_availability(self) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.CRUSOE,
            locations=self.config.regions or None,
            catalog=self._catalog,
        )
        quota_map = self._get_quota_map()
        result = []
        for offer in offers:
            family = _get_instance_family(offer.instance.name)
            availability = InstanceAvailability.UNKNOWN
            for prog_name, available in quota_map.items():
                if family.startswith(prog_name) or prog_name.startswith(family):
                    availability = (
                        InstanceAvailability.AVAILABLE
                        if available > 0
                        else InstanceAvailability.NO_QUOTA
                    )
                    break
            result.append(
                InstanceOfferWithAvailability(
                    **offer.dict(),
                    availability=availability,
                )
            )
        return result

    def _get_quota_map(self) -> dict[str, int]:
        try:
            quotas = self._client.list_quotas()
        except Exception:
            logger.warning("Failed to fetch Crusoe quotas, availability will be UNKNOWN")
            return {}
        result = {}
        for q in quotas:
            prog_name = q.get("programmatic_name", "")
            available = q.get("available", 0)
            category = q.get("category", "")
            if "Instance" in category:
                result[prog_name] = available
        return result

    def get_offers_modifiers(self, requirements: Requirements) -> Iterable[OfferModifier]:
        # Only adjust disk size for types without ephemeral NVMe (disk_gb == 0).
        # Types with ephemeral NVMe already have their disk_size set by gpuhunt.
        base_modifier = get_offers_disk_modifier(CONFIGURABLE_DISK_SIZE, requirements)

        def modifier(
            offer: InstanceOfferWithAvailability,
        ) -> Optional[InstanceOfferWithAvailability]:
            if _has_ephemeral_disk(offer):
                return offer
            return base_modifier(offer)

        return [modifier]

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name(instance_config)
        region = instance_offer.region

        ib_partition_id = None
        if placement_group:
            assert placement_group.provisioning_data is not None
            pg_data = CrusoePlacementGroupBackendData.load(
                placement_group.provisioning_data.backend_data
            )
            ib_partition_id = pg_data.ib_partition_id

        gpus = instance_offer.instance.resources.gpus
        gpu_type = gpus[0].name if gpus else ""
        instance_type_name = instance_offer.instance.name
        image = _get_image(instance_type_name, gpu_type)

        needs_data_disk = not _has_ephemeral_disk(instance_offer)
        # Always include storage setup: it auto-detects /dev/vdb (data disk) or
        # /dev/nvme* (ephemeral NVMe) and moves containerd storage there.
        commands = SETUP_COMMANDS + STORAGE_SETUP_COMMANDS + get_shim_commands(is_privileged=True)
        startup_script = "#!/bin/bash\nset -e\n" + " && ".join(commands)

        data_disk_id = None
        create_op = None
        try:
            if needs_data_disk:
                disk_size_mib = instance_offer.instance.resources.disk.size_mib
                disk_size_gib = max(disk_size_mib // 1024, 1)
                disk_op = self._client.create_disk(
                    name=f"{instance_name}-data",
                    size=f"{disk_size_gib}GiB",
                    location=region,
                )
                data_disk_id = disk_op["metadata"]["id"]
                self._client.wait_for_disk_operation(
                    disk_op["operation_id"], timeout=WAIT_FOR_DISK_TIMEOUT
                )

            disks = None
            if data_disk_id:
                disks = [
                    {"disk_id": data_disk_id, "mode": "read-write", "attachment_type": "data"}
                ]

            host_channel_adapters = None
            if ib_partition_id:
                host_channel_adapters = [{"ib_partition_id": ib_partition_id}]

            create_op = self._client.create_vm(
                name=instance_name,
                vm_type=instance_type_name,
                location=region,
                ssh_public_key=instance_config.get_public_keys()[0],
                image=image,
                startup_script=startup_script,
                disks=disks,
                host_channel_adapters=host_channel_adapters,
            )
            vm_id = create_op["metadata"]["id"]
            self._client.wait_for_vm_operation(
                create_op["operation_id"], timeout=WAIT_FOR_VM_TIMEOUT
            )
        except BaseException:
            if create_op is not None:
                vm_id_to_delete = create_op.get("metadata", {}).get("id")
                if vm_id_to_delete:
                    try:
                        self._client.delete_vm(vm_id_to_delete)
                    except Exception as e:
                        logger.exception("Could not delete VM %s: %s", vm_id_to_delete, e)
            if data_disk_id:
                try:
                    self._client.delete_disk(data_disk_id)
                except Exception as e:
                    logger.exception("Could not delete disk %s: %s", data_disk_id, e)
            raise

        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=vm_id,
            hostname=None,
            region=region,
            price=instance_offer.price,
            ssh_port=22,
            username="ubuntu",
            dockerized=True,
            backend_data=CrusoeInstanceBackendData(data_disk_id=data_disk_id).json(),
        )

    def update_provisioning_data(
        self, provisioning_data, project_ssh_public_key, project_ssh_private_key
    ):
        try:
            vm = self._client.get_vm(provisioning_data.instance_id)
        except Exception:
            return
        interfaces = vm.get("network_interfaces", [])
        if not interfaces:
            return
        ips = interfaces[0].get("ips", [])
        if not ips:
            return
        public_ipv4 = ips[0].get("public_ipv4", {})
        private_ipv4 = ips[0].get("private_ipv4", {})
        if public_ipv4.get("address"):
            provisioning_data.hostname = public_ipv4["address"]
        if private_ipv4.get("address"):
            provisioning_data.internal_ip = private_ipv4["address"]

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        backend_data_parsed = CrusoeInstanceBackendData.load(backend_data)
        try:
            vm = self._client.get_vm(instance_id)
        except BackendError:
            # VM not found (404) or other API error -- treat as already deleted
            vm = None

        if vm is not None:
            state = vm.get("state", "")
            if state not in ("STATE_DELETING", "STATE_DELETED"):
                try:
                    self._client.delete_vm(instance_id)
                except BackendError:
                    pass
                raise NotYetTerminated(f"Requested VM deletion. State was: {state}")
            else:
                raise NotYetTerminated(f"Waiting for VM deletion. State: {state}")

        # OS disk is auto-deleted with the VM. Data disk must be deleted separately.
        if backend_data_parsed.data_disk_id:
            try:
                self._client.delete_disk(backend_data_parsed.data_disk_id)
            except BackendError:
                pass

    def create_placement_group(
        self,
        placement_group: PlacementGroup,
        master_instance_offer: InstanceOffer,
    ) -> PlacementGroupProvisioningData:
        assert placement_group.configuration.placement_strategy == PlacementStrategy.CLUSTER
        instance_name = master_instance_offer.instance.name
        region = placement_group.configuration.region

        if not _is_ib_type(instance_name):
            return PlacementGroupProvisioningData(
                backend=BackendType.CRUSOE,
                backend_data=CrusoePlacementGroupBackendData(
                    ib_partition_id=None, ib_network_id=None
                ).json(),
            )

        ib_networks = self._client.list_ib_networks()
        target_network = None
        for net in ib_networks:
            if net.get("location") != region:
                continue
            for cap in net.get("capacities", []):
                if cap.get("slice_type") == instance_name:
                    target_network = net
                    break
            if target_network:
                break

        if target_network is None:
            raise BackendError(
                f"No IB network found in {region} for instance type {instance_name}"
            )

        partition = self._client.create_ib_partition(
            name=placement_group.name,
            ib_network_id=target_network["id"],
        )
        return PlacementGroupProvisioningData(
            backend=BackendType.CRUSOE,
            backend_data=CrusoePlacementGroupBackendData(
                ib_partition_id=partition["id"],
                ib_network_id=target_network["id"],
            ).json(),
        )

    def delete_placement_group(self, placement_group: PlacementGroup) -> None:
        assert placement_group.provisioning_data is not None
        pg_data = CrusoePlacementGroupBackendData.load(
            placement_group.provisioning_data.backend_data
        )
        if pg_data.ib_partition_id:
            try:
                self._client.delete_ib_partition(pg_data.ib_partition_id)
            except BackendError:
                pass

    def is_suitable_placement_group(
        self,
        placement_group: PlacementGroup,
        instance_offer: InstanceOffer,
    ) -> bool:
        if placement_group.configuration.region != instance_offer.region:
            return False
        assert placement_group.provisioning_data is not None
        pg_data = CrusoePlacementGroupBackendData.load(
            placement_group.provisioning_data.backend_data
        )
        if pg_data.ib_partition_id is None:
            return not _is_ib_type(instance_offer.instance.name)
        return _is_ib_type(instance_offer.instance.name)


class CrusoeInstanceBackendData(CoreModel):
    data_disk_id: Optional[str] = None

    @classmethod
    def load(cls, raw: Optional[str]) -> "CrusoeInstanceBackendData":
        if raw is None:
            return cls()
        return cls.__response__.parse_raw(raw)


class CrusoePlacementGroupBackendData(CoreModel):
    ib_partition_id: Optional[str] = None
    ib_network_id: Optional[str] = None

    @classmethod
    def load(cls, raw: Optional[str]) -> "CrusoePlacementGroupBackendData":
        if raw is None:
            return cls()
        return cls.__response__.parse_raw(raw)
