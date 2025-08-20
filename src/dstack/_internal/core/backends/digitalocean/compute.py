from typing import List, Optional

import gpuhunt
from gpuhunt.providers.digitalocean import DigitalOceanProvider

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    generate_unique_instance_name,
    get_user_data,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.digitalocean.api_client import DigitalOceanAPIClient
from dstack._internal.core.backends.digitalocean.models import DigitalOceanConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

MAX_INSTANCE_NAME_LEN = 60

# Setup commands for DigitalOcean instances
SETUP_COMMANDS = [
    "sudo ufw delete limit ssh",
    "sudo ufw allow ssh",
]

DOCKER_INSTALL_COMMANDS = [
    "export DEBIAN_FRONTEND=noninteractive",
    "mkdir -p /etc/apt/keyrings",
    "curl --max-time 60 -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
    'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null',
    "apt-get update",
    "apt-get --assume-yes install docker-ce docker-ce-cli containerd.io docker-compose-plugin",
]


class DigitalOceanCompute(
    ComputeWithCreateInstanceSupport,
    Compute,
):
    def __init__(self, config: DigitalOceanConfig):
        super().__init__()
        self.config = config
        self.api_client = DigitalOceanAPIClient(config.creds.api_key, config.flavor or "standard")
        self.catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self.catalog.add_provider(
            DigitalOceanProvider(token=config.creds.api_key, flavor=config.flavor or "standard")
        )
        # self.catalog.add_provider(
        #     DigitalOceanProvider(token=config.creds.api_key, flavor="standard")
        # )

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.DIGITALOCEAN,
            locations=self.config.regions,
            requirements=requirements,
            catalog=self.catalog,
        )
        return [
            InstanceOfferWithAvailability(
                **offer.dict(),
                availability=InstanceAvailability.AVAILABLE,
            )
            for offer in offers
        ]

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name(
            instance_config, max_length=MAX_INSTANCE_NAME_LEN
        )

        project_ssh_key = instance_config.ssh_keys[0]
        ssh_key_id = self.api_client.get_or_create_ssh_key(
            name=f"dstack-{instance_config.project_name}",
            public_key=project_ssh_key.public,
        )

        # Use the instance name directly from the offer (gpuhunt handles flavor-specific naming)
        size_slug = instance_offer.instance.name

        if not instance_offer.instance.resources.gpus:
            backend_specific_commands = SETUP_COMMANDS + DOCKER_INSTALL_COMMANDS
        else:
            backend_specific_commands = SETUP_COMMANDS

        # Prepare droplet configuration
        droplet_config = {
            "name": instance_name,
            "region": instance_offer.region,
            "size": size_slug,
            "image": self._get_image_for_instance(instance_offer),
            "ssh_keys": [ssh_key_id],
            "backups": False,
            "ipv6": False,
            "monitoring": False,
            "tags": [],
            "user_data": get_user_data(
                authorized_keys=instance_config.get_public_keys(),
                backend_specific_commands=backend_specific_commands,
            ),
        }

        droplet = self.api_client.create_droplet(droplet_config)

        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=str(droplet["id"]),
            hostname=None,  # Will be set when droplet is active
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="root",
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
    ):
        droplet = self.api_client.get_droplet(provisioning_data.instance_id)
        if droplet["status"] == "active":
            for network in droplet["networks"]["v4"]:
                if network["type"] == "public":
                    provisioning_data.hostname = network["ip_address"]
                    break

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        self.api_client.delete_droplet(instance_id)

    def _get_image_for_instance(self, instance_offer: InstanceOfferWithAvailability) -> str:
        if not instance_offer.instance.resources.gpus:
            # No GPUs, use CPU image
            return "ubuntu-24-04-x64"

        gpu_count = len(instance_offer.instance.resources.gpus)
        gpu_name = instance_offer.instance.resources.gpus[0].name

        if gpu_name == "MI300X":
            # AMD GPU
            return "digitaloceanai-rocmjupyter"
        else:
            # NVIDIA GPUs - DO only supports 1 and 8 GPU configurations.
            # DO says for single GPU plans using GPUs other than H100s use "gpu-h100x1-base". But for x8 assuming same.
            # See (https://docs.digitalocean.com/products/droplets/getting-started/recommended-gpu-setup/#aiml-ready-image)
            if gpu_count == 8:
                return "gpu-h100x8-base"
            elif gpu_count == 1:
                return "gpu-h100x1-base"
            else:
                # For Unsupported GPU count - use single GPU image and log warning
                logger.warning(
                    f"Unsupported NVIDIA GPU count: {gpu_count}, using single GPU image"
                )
                return "gpu-h100x1-base"
