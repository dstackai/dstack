import json
from typing import List, Optional

import requests

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    generate_unique_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.tensordock.api_client import TensorDockAPIClient
from dstack._internal.core.backends.tensordock.models import TensorDockConfig
from dstack._internal.core.errors import NoCapacityError
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


# Undocumented but names of len 60 work
MAX_INSTANCE_NAME_LEN = 60


class TensorDockCompute(
    ComputeWithCreateInstanceSupport,
    Compute,
):
    def __init__(self, config: TensorDockConfig):
        super().__init__()
        self.config = config
        self.api_client = TensorDockAPIClient(config.creds.api_key, config.creds.api_token)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.TENSORDOCK,
            requirements=requirements,
        )
        offers = [
            InstanceOfferWithAvailability(
                **offer.dict(), availability=InstanceAvailability.AVAILABLE
            )
            for offer in offers
        ]
        return offers

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name(
            instance_config, max_length=MAX_INSTANCE_NAME_LEN
        )
        commands = get_shim_commands(authorized_keys=instance_config.get_public_keys())
        try:
            resp = self.api_client.deploy_single(
                instance_name=instance_name,
                instance=instance_offer.instance,
                cloudinit={
                    "ssh_pwauth": False,  # disable password auth
                    "users": [
                        "default",
                        {
                            "name": "user",
                            "ssh_authorized_keys": instance_config.get_public_keys(),
                        },
                    ],
                    "runcmd": [
                        ["sh", "-c", " && ".join(commands)],
                    ],
                    "write_files": [
                        {
                            "path": "/etc/docker/daemon.json",
                            "content": json.dumps(
                                {
                                    "runtimes": {
                                        "nvidia": {
                                            "path": "nvidia-container-runtime",
                                            "runtimeArgs": [],
                                        }
                                    },
                                    "exec-opts": ["native.cgroupdriver=cgroupfs"],
                                }
                            ),
                        }
                    ],
                },
            )
        except requests.HTTPError as e:
            logger.warning("Got error from tensordock: %s", e)
            raise NoCapacityError()
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=resp["server"],
            hostname=resp["ip"],
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="user",
            ssh_port={int(v): int(k) for k, v in resp["port_forwards"].items()}[22],
            dockerized=True,
            ssh_proxy=None,
            backend_data=None,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        self.api_client.delete_single_if_exists(instance_id)
