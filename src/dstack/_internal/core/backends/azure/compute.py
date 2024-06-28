import base64
import enum
import re
from typing import List, Optional, Tuple

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceExistsError
from azure.mgmt import compute as compute_mgmt
from azure.mgmt import network as network_mgmt
from azure.mgmt.compute.models import (
    DiskCreateOptionTypes,
    HardwareProfile,
    ImageReference,
    LinuxConfiguration,
    ManagedDiskParameters,
    NetworkProfile,
    OSDisk,
    OSProfile,
    ResourceIdentityType,
    ResourceSku,
    SshConfiguration,
    SshPublicKey,
    StorageAccountTypes,
    StorageProfile,
    SubResource,
    UserAssignedIdentitiesValue,
    VirtualMachine,
    VirtualMachineIdentity,
    VirtualMachineNetworkInterfaceConfiguration,
    VirtualMachineNetworkInterfaceIPConfiguration,
    VirtualMachinePublicIPAddressConfiguration,
)

from dstack import version
from dstack._internal.core.backends.azure import utils as azure_utils
from dstack._internal.core.backends.azure.config import AzureConfig
from dstack._internal.core.backends.base.compute import (
    Compute,
    get_gateway_user_data,
    get_instance_name,
    get_user_data,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.errors import NoCapacityError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import (
    GatewayComputeConfiguration,
    GatewayProvisioningData,
)
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class AzureCompute(Compute):
    def __init__(self, config: AzureConfig, credential: TokenCredential):
        self.config = config
        self.credential = credential
        self._compute_client = compute_mgmt.ComputeManagementClient(
            credential=credential, subscription_id=config.subscription_id
        )
        self._network_client = network_mgmt.NetworkManagementClient(
            credential=credential, subscription_id=config.subscription_id
        )

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.AZURE,
            locations=self.config.locations,
            requirements=requirements,
            extra_filter=_supported_instances,
        )
        offers_with_availability = _get_offers_with_availability(
            compute_client=self._compute_client,
            config_locations=self.config.locations,
            offers=offers,
        )
        return offers_with_availability

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> JobProvisioningData:
        location = instance_offer.region
        logger.info(
            "Requesting %s %s instance in %s...",
            instance_offer.instance.name,
            "spot" if instance_offer.instance.resources.spot else "",
            location,
        )
        ssh_pub_keys = instance_config.get_public_keys()
        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
        vm = _launch_instance(
            compute_client=self._compute_client,
            subscription_id=self.config.subscription_id,
            location=location,
            resource_group=self.config.resource_group,
            network_security_group=azure_utils.get_default_network_security_group_name(
                resource_group=self.config.resource_group,
                location=location,
            ),
            network=azure_utils.get_default_network_name(
                resource_group=self.config.resource_group,
                location=location,
            ),
            subnet=azure_utils.get_default_subnet_name(
                resource_group=self.config.resource_group,
                location=location,
            ),
            managed_identity=None,
            image_reference=_get_image_ref(
                compute_client=self._compute_client,
                location=location,
                variant=VMImageVariant.from_instance_type(instance_offer.instance),
            ),
            vm_size=instance_offer.instance.name,
            # instance_name includes region because Azure may create an instance resource
            # even when provisioning fails.
            instance_name=f"{instance_config.instance_name}-{instance_offer.region}",
            user_data=get_user_data(authorized_keys=ssh_pub_keys),
            ssh_pub_keys=ssh_pub_keys,
            spot=instance_offer.instance.resources.spot,
            disk_size=disk_size,
            computer_name="runnervm",
        )
        logger.info("Request succeeded")
        public_ip, private_ip = _get_vm_public_private_ips(
            network_client=self._network_client,
            resource_group=self.config.resource_group,
            vm=vm,
        )
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=vm.name,
            hostname=public_ip,
            internal_ip=private_ip,
            region=location,
            price=instance_offer.price,
            username="ubuntu",
            ssh_port=22,
            dockerized=True,
            ssh_proxy=None,
            backend_data=None,
        )

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
    ) -> JobProvisioningData:
        instance_config = InstanceConfiguration(
            project_name=run.project_name,
            instance_name=get_instance_name(run, job),  # TODO: generate name
            ssh_keys=[
                SSHKey(public=project_ssh_public_key.strip()),
            ],
            job_docker_config=None,
            user=run.user,
        )
        return self.create_instance(instance_offer, instance_config)

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        _terminate_instance(
            compute_client=self._compute_client,
            resource_group=self.config.resource_group,
            instance_name=instance_id,
        )

    def create_gateway(
        self,
        configuration: GatewayComputeConfiguration,
    ) -> GatewayProvisioningData:
        logger.info(
            "Launching %s gateway instance in %s...",
            configuration.instance_name,
            configuration.region,
        )
        vm = _launch_instance(
            compute_client=self._compute_client,
            subscription_id=self.config.subscription_id,
            location=configuration.region,
            resource_group=self.config.resource_group,
            network_security_group=azure_utils.get_gateway_network_security_group_name(
                resource_group=self.config.resource_group,
                location=configuration.region,
            ),
            network=azure_utils.get_default_network_name(
                resource_group=self.config.resource_group,
                location=configuration.region,
            ),
            subnet=azure_utils.get_default_subnet_name(
                resource_group=self.config.resource_group,
                location=configuration.region,
            ),
            managed_identity=None,
            image_reference=_get_gateway_image_ref(),
            vm_size="Standard_B1s",
            instance_name=configuration.instance_name,
            user_data=get_gateway_user_data(configuration.ssh_key_pub),
            ssh_pub_keys=[configuration.ssh_key_pub],
            spot=False,
            disk_size=30,
            computer_name="gatewayvm",
        )
        logger.info("Request succeeded")
        public_ip, _ = _get_vm_public_private_ips(
            network_client=self._network_client,
            resource_group=self.config.resource_group,
            vm=vm,
        )
        return GatewayProvisioningData(
            instance_id=vm.name,
            ip_address=public_ip,
            region=configuration.region,
        )

    def terminate_gateway(
        self,
        instance_id: str,
        configuration: GatewayComputeConfiguration,
        backend_data: Optional[str] = None,
    ):
        self.terminate_instance(
            instance_id=instance_id,
            region=configuration.region,
            backend_data=backend_data,
        )


class VMImageVariant(enum.Enum):
    GRID = enum.auto()
    CUDA = enum.auto()
    STANDARD = enum.auto()

    @classmethod
    def from_instance_type(cls, instance: InstanceType) -> "VMImageVariant":
        if "_A10_v5" in instance.name:
            return cls.GRID
        elif len(instance.resources.gpus) > 0:
            return cls.CUDA
        else:
            return cls.STANDARD

    def get_image_name(self) -> str:
        name = "dstack-"
        if self is self.GRID:
            name += "grid-"
        elif self is self.CUDA:
            name += "cuda-"
        name += version.base_image
        return name


_SUPPORTED_VM_SERIES_PATTERNS = [
    r"D(\d+)s_v3",  # Dsv3-series
    r"E(\d+)i?s_v4",  # Esv4-series
    r"E(\d+)-(\d+)s_v4",  # Esv4-series (constrained vCPU)
    r"NC(\d+)s_v3",  # NCv3-series [V100 16GB]
    r"NC(\d+)as_T4_v3",  # NCasT4_v3-series [T4]
    r"ND(\d+)rs_v2",  # NDv2-series [8xV100 32GB]
    r"NV(\d+)adm?s_A10_v5",  # NVadsA10 v5-series [A10]
    r"NC(\d+)ads_A100_v4",  # NC A100 v4-series [A100 80GB]
    r"ND(\d+)asr_v4",  # ND A100 v4-series [8xA100 40GB]
    r"ND(\d+)amsr_A100_v4",  # NDm A100 v4-series [8xA100 80GB]
]
_SUPPORTED_VM_SERIES_PATTERN = (
    "^Standard_(" + "|".join(f"({s})" for s in _SUPPORTED_VM_SERIES_PATTERNS) + ")$"
)


def _supported_instances(offer: InstanceOffer) -> bool:
    m = re.match(_SUPPORTED_VM_SERIES_PATTERN, offer.instance.name)
    return m is not None


def _get_offers_with_availability(
    compute_client: compute_mgmt.ComputeManagementClient,
    config_locations: List[str],
    offers: List[InstanceOffer],
) -> List[InstanceOfferWithAvailability]:
    offers = [offer for offer in offers if offer.region in config_locations]
    locations = set(offer.region for offer in offers)

    has_quota = set()
    for location in locations:
        resources = compute_client.resource_skus.list(filter=f"location eq '{location}'")
        for resource in resources:
            if resource.resource_type != "virtualMachines" or not _vm_type_available(resource):
                continue
            has_quota.add((resource.name, location))

    offers_with_availability = []
    for offer in offers:
        availability = InstanceAvailability.NO_QUOTA
        if (offer.instance.name, offer.region) in has_quota:
            availability = InstanceAvailability.UNKNOWN
        offers_with_availability.append(
            InstanceOfferWithAvailability(**offer.dict(), availability=availability)
        )

    return offers_with_availability


def _vm_type_available(vm_resource: ResourceSku) -> bool:
    if len(vm_resource.restrictions) == 0:
        return True
    # If a VM type is restricted in "Zone", it is still available in other zone.
    # Otherwise the restriction type is "Location"
    if vm_resource.restrictions[0].type == "Zone":
        return True
    return False


def _get_image_ref(
    compute_client: compute_mgmt.ComputeManagementClient,
    location: str,
    variant: VMImageVariant,
) -> ImageReference:
    image = compute_client.community_gallery_images.get(
        location=location,
        public_gallery_name="dstack-ebac134d-04b9-4c2b-8b6c-ad3e73904aa7",  # Gen2
        gallery_image_name=variant.get_image_name(),
    )
    return ImageReference(community_gallery_image_id=image.unique_id)


def _get_gateway_image_ref() -> ImageReference:
    return ImageReference(
        publisher="canonical",
        offer="0001-com-ubuntu-server-jammy",
        sku="22_04-lts",
        version="latest",
    )


def _launch_instance(
    compute_client: compute_mgmt.ComputeManagementClient,
    subscription_id: str,
    location: str,
    resource_group: str,
    network_security_group: str,
    network: str,
    subnet: str,
    managed_identity: Optional[str],
    image_reference: ImageReference,
    vm_size: str,
    instance_name: str,
    user_data: str,
    ssh_pub_keys: List[str],
    spot: bool,
    disk_size: int,
    computer_name: str,
) -> VirtualMachine:
    try:
        poller = compute_client.virtual_machines.begin_create_or_update(
            resource_group,
            instance_name,
            VirtualMachine(
                location=location,
                hardware_profile=HardwareProfile(vm_size=vm_size),
                storage_profile=StorageProfile(
                    image_reference=image_reference,
                    os_disk=OSDisk(
                        create_option=DiskCreateOptionTypes.FROM_IMAGE,
                        managed_disk=ManagedDiskParameters(
                            storage_account_type=StorageAccountTypes.STANDARD_SSD_LRS
                        ),
                        disk_size_gb=disk_size,
                        delete_option="Delete",
                    ),
                ),
                os_profile=OSProfile(
                    computer_name=computer_name,
                    admin_username="ubuntu",
                    linux_configuration=LinuxConfiguration(
                        ssh=SshConfiguration(
                            public_keys=[
                                SshPublicKey(
                                    path="/home/ubuntu/.ssh/authorized_keys",
                                    key_data=ssh_pub_key,
                                )
                                for ssh_pub_key in ssh_pub_keys
                            ]
                        )
                    ),
                ),
                network_profile=NetworkProfile(
                    network_api_version=network_mgmt.NetworkManagementClient.DEFAULT_API_VERSION,
                    network_interface_configurations=[
                        VirtualMachineNetworkInterfaceConfiguration(
                            name="nic_config",
                            network_security_group=SubResource(
                                id=azure_utils.get_network_security_group_id(
                                    subscription_id,
                                    resource_group,
                                    network_security_group,
                                )
                            ),
                            ip_configurations=[
                                VirtualMachineNetworkInterfaceIPConfiguration(
                                    name="ip_config",
                                    subnet=SubResource(
                                        id=azure_utils.get_subnet_id(
                                            subscription_id,
                                            resource_group,
                                            network,
                                            subnet,
                                        )
                                    ),
                                    public_ip_address_configuration=VirtualMachinePublicIPAddressConfiguration(
                                        name="public_ip_config",
                                    ),
                                )
                            ],
                        )
                    ],
                ),
                priority="Spot" if spot else "Regular",
                eviction_policy="Delete" if spot else None,
                identity=None
                if managed_identity is None
                else VirtualMachineIdentity(
                    type=ResourceIdentityType.USER_ASSIGNED,
                    user_assigned_identities={
                        azure_utils.get_managed_identity_id(
                            subscription_id, resource_group, managed_identity
                        ): UserAssignedIdentitiesValue()
                    },
                ),
                user_data=base64.b64encode(user_data.encode()).decode(),
            ),
        )
    except ResourceExistsError as e:
        # May occur if no quota or quota exceeded
        if e.error is not None and e.error.code in ["SkuNotAvailable", "OperationNotAllowed"]:
            message = e.error.message if e.error.message is not None else ""
            raise NoCapacityError(message)
        raise e
    vm = poller.result()
    return vm


def _get_vm_public_private_ips(
    network_client: network_mgmt.NetworkManagementClient,
    resource_group: str,
    vm: VirtualMachine,
) -> Tuple[str, str]:
    nic_id = vm.network_profile.network_interfaces[0].id
    nic_name = azure_utils.get_resource_name_from_resource_id(nic_id)
    nic = network_client.network_interfaces.get(
        resource_group_name=resource_group,
        network_interface_name=nic_name,
    )
    public_ip_id = nic.ip_configurations[0].public_ip_address.id
    public_ip_name = azure_utils.get_resource_name_from_resource_id(public_ip_id)
    public_ip = network_client.public_ip_addresses.get(resource_group, public_ip_name)

    private_ip = nic.ip_configurations[0].private_ip_address
    return public_ip.ip_address, private_ip


def _terminate_instance(
    compute_client: compute_mgmt.ComputeManagementClient,
    resource_group: str,
    instance_name: str,
):
    compute_client.virtual_machines.begin_delete(
        resource_group_name=resource_group,
        vm_name=instance_name,
    )
