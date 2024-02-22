import time
from typing import List, Optional

import gpuhunt
import requests
from gpuhunt.providers.vastai import VastAIProvider

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import get_docker_commands, get_instance_name
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.vastai.api_client import DISK_SIZE, VastAIAPIClient
from dstack._internal.core.backends.vastai.config import VastAIConfig
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
POLLING_INTERVAL = 10


class VastAICompute(Compute):
    def __init__(self, config: VastAIConfig):
        self.config = config
        self.api_client = VastAIAPIClient(config.creds.api_key)
        self.catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self.catalog.add_provider(
            VastAIProvider(
                extra_filters={
                    "direct_port_count": {"gte": 1},
                    "reliability2": {"gte": 0.9},
                    "inet_down": {"gt": 128},
                    "verified": {"eq": True},
                    "cuda_max_good": {"gte": 11.8},
                    "disk_space": {"gte": DISK_SIZE},
                }
            )
        )

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.VASTAI,
            requirements=requirements,
            # TODO(egor-s): spots currently not supported
            extra_filter=lambda offer: not offer.instance.resources.spot,
            catalog=self.catalog,
        )
        offers = [
            InstanceOfferWithAvailability(
                **offer.dict(),
                availability=InstanceAvailability.AVAILABLE,
                instance_runtime=InstanceRuntime.RUNNER,
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
        commands = get_docker_commands(
            [run.run_spec.ssh_key_pub.strip(), project_ssh_public_key.strip()]
        )
        registry_auth = None  # TODO(egor-s): registry auth secrets
        resp = self.api_client.create_instance(
            instance_name=get_instance_name(run, job),
            bundle_id=instance_offer.instance.name,
            image_name=job.job_spec.image_name,
            onstart=" && ".join(commands),
            registry_auth=registry_auth,
        )
        instance_id = resp["new_contract"]
        try:
            while (resp := self.api_client.get_instance(instance_id))[
                "actual_status"
            ] != "running":
                if (
                    resp["actual_status"] == "created"
                    and ": OCI runtime create failed:" in resp["status_msg"]
                ):
                    raise ComputeError(resp["status_msg"])
                # if resp["actual_status"] == "exited":
                #     raise ComputeError(resp["status_msg"])
                logger.debug(
                    "Waiting %s: %s", instance_id, {k: v for k, v in resp.items() if "stat" in k}
                )
                time.sleep(POLLING_INTERVAL)

        except (requests.HTTPError, ComputeError):
            logger.warning("Failed to launch instance %s, request termination", instance_id)
            self.terminate_instance(instance_id, instance_offer.region)
            raise
        return LaunchedInstanceInfo(
            instance_id=instance_id,
            ip_address=resp["public_ipaddr"].strip(),
            region=instance_offer.region,
            username="root",
            ssh_port=int(resp["ports"]["10022/tcp"][0]["HostPort"]),
            dockerized=False,
            ssh_proxy=None,
            backend_data=None,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        self.api_client.destroy_instance(instance_id)
