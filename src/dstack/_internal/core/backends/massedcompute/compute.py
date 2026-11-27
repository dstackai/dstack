import shlex
from typing import Optional

import gpuhunt
from gpuhunt.providers.massedcompute import MassedComputeProvider

from dstack._internal.core.backends.base.authorized_keys import get_add_authorized_keys_script
from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithResourceListingSupport,
    generate_unique_instance_name,
    get_shim_commands,
    parse_provider_ref_from_name,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.massedcompute.api_client import MassedComputeAPIClient
from dstack._internal.core.backends.massedcompute.models import MassedComputeConfig
from dstack._internal.core.errors import NotYetTerminated, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import (
    ListedResourceGroup,
    OwnerType,
    ResourceListing,
)
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import JobProvisioningData


class MassedComputeCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithResourceListingSupport,
    Compute,
):
    def __init__(self, config: MassedComputeConfig):
        super().__init__()
        self.api_client = MassedComputeAPIClient(config.creds.api_key)
        self.catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self.catalog.add_provider(MassedComputeProvider(config.creds.api_key))

    def get_all_offers_with_availability(
        self, unallocated_resources: bool
    ) -> list[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(backend=BackendType.MASSEDCOMPUTE, catalog=self.catalog)
        return [
            offer.with_availability(availability=InstanceAvailability.AVAILABLE)
            for offer in offers
        ]

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        name = generate_unique_instance_name(instance_config, with_provider_ref=True)
        # The image's SSH user is case-sensitive. The startup command runs as root.
        key_script = get_add_authorized_keys_script(instance_config.get_public_keys())
        install_keys = shlex.join(["sudo", "-H", "-u", "Ubuntu", "sh", "-c", key_script])
        command = " && ".join(
            [install_keys, *get_shim_commands(arch=instance_offer.instance.resources.cpu_arch)]
        )
        instance_id = self.api_client.launch(name, instance_offer.instance.name, command)
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_id,
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="Ubuntu",
            ssh_port=22,
            dockerized=True,
            ssh_proxy=None,
            backend_data=None,
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> None:
        instance = self.api_client.get_instance(provisioning_data.instance_id)
        if instance is None:
            return
        if instance.status.lower() == "stopped":
            raise ProvisioningError("MassedCompute instance stopped during provisioning")
        if instance.os_booted and instance.ip and instance.username:
            provisioning_data.hostname = instance.ip
            provisioning_data.username = instance.username

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        instance = self.api_client.get_instance(instance_id)
        if instance is None:
            return
        if instance.status.lower() not in {"terminating", "deleting"}:
            self.api_client.terminate(instance_id)
        raise NotYetTerminated(f"Waiting for MassedCompute instance {instance_id} to terminate")

    def list_resource_groups(self) -> ResourceListing:
        groups = []
        for instance in self.api_client.list_instances():
            provider_ref = parse_provider_ref_from_name(instance.name)
            if provider_ref is None or instance.status.lower() in {"terminating", "deleting"}:
                continue
            groups.append(
                ListedResourceGroup(
                    backend=BackendType.MASSEDCOMPUTE,
                    owner_type=OwnerType.INSTANCE,
                    provider_ref=provider_ref,
                    primary_id=instance.uuid,
                    region="any",
                    created_at=instance.created,
                    description=instance.name,
                    backend_data=None,
                )
            )
        return ResourceListing(resource_groups=groups)

    def delete_resource_group(self, group: ListedResourceGroup) -> None:
        if group.primary_id is not None:
            self.terminate_instance(group.primary_id, "any")
