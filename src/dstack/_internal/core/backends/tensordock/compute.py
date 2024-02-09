import json
from typing import List, Optional

import requests

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import get_instance_name, get_shim_commands
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.tensordock.api_client import TensorDockAPIClient
from dstack._internal.core.backends.tensordock.config import TensorDockConfig
from dstack._internal.core.errors import NoCapacityError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class TensorDockCompute(Compute):
    def __init__(self, config: TensorDockConfig):
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

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        commands = get_shim_commands(
            backend=BackendType.TENSORDOCK,
            image_name=job.job_spec.image_name,
            authorized_keys=[
                run.run_spec.ssh_key_pub.strip(),
                project_ssh_public_key.strip(),
            ],
            registry_auth_required=job.job_spec.registry_auth is not None,
        )
        try:
            resp = self.api_client.deploy_single(
                instance_name=get_instance_name(run, job),
                instance=instance_offer.instance,
                cloudinit={
                    "ssh_pwauth": False,  # disable password auth
                    "users": [
                        "default",
                        {
                            "name": "user",
                            "ssh_authorized_keys": [
                                run.run_spec.ssh_key_pub.strip(),
                                project_ssh_public_key.strip(),
                            ],
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
        return LaunchedInstanceInfo(
            instance_id=resp["server"],
            ip_address=resp["ip"],
            region=instance_offer.region,
            username="user",
            ssh_port={v: k for k, v in resp["port_forwards"].items()}["22"],
            dockerized=True,
            ssh_proxy=None,
            backend_data=None,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        try:
            self.api_client.delete_single(instance_id)
        except requests.HTTPError:
            pass
