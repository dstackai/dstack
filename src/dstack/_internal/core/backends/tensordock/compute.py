import json
from typing import List, Optional

import requests

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import get_instance_name, get_shim_commands
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.tensordock.api_client import TensorDockAPIClient
from dstack._internal.core.backends.tensordock.config import TensorDockConfig
from dstack._internal.core.errors import BackendError, NoCapacityError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
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

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> JobProvisioningData:
        commands = get_shim_commands(authorized_keys=instance_config.get_public_keys())
        try:
            resp = self.api_client.deploy_single(
                instance_name=instance_config.instance_name,
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
            ssh_port={v: k for k, v in resp["port_forwards"].items()}["22"],
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
                SSHKey(public=run.run_spec.ssh_key_pub.strip()),
                SSHKey(public=project_ssh_public_key.strip()),
            ],
            job_docker_config=None,
            user=run.user,
        )
        return self.create_instance(instance_offer, instance_config)

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        try:
            self.api_client.delete_single(instance_id)
        except requests.HTTPError as e:
            logger.error(
                "An HTTP error occurred when trying to terminate TensorDock instance %s: %s",
                instance_id,
                e,
            )
        except BackendError as e:
            logger.error(
                "TensorDock returned an error when trying to terminate instance %s: %s",
                instance_id,
                e,
            )
