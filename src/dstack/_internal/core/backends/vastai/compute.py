import time
from typing import List, Optional

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import get_docker_commands
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.vastai.api_client import VastAIAPIClient
from dstack._internal.core.backends.vastai.config import VastAIConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run


class VastAICompute(Compute):
    def __init__(self, config: VastAIConfig):
        self.config = config
        self.api_client = VastAIAPIClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            provider=BackendType.VASTAI.value,
            # TODO(egor-s): locations
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
        commands = get_docker_commands(
            [run.run_spec.ssh_key_pub.strip(), project_ssh_public_key.strip()]
        )
        registry_auth = None  # TODO(egor-s): registry auth secrets
        resp = self.api_client.create_instance(
            instance_name=job.job_spec.job_name,
            bundle_id=instance_offer.instance.name,
            image_name=job.job_spec.image_name,
            onstart=" && ".join(commands),
            registry_auth=registry_auth,
        )
        instance_id = resp["new_contract"]
        while (resp := self.api_client.get_instance(instance_id))["actual_status"] != "running":
            time.sleep(5)
        return LaunchedInstanceInfo(
            instance_id=instance_id,
            ip_address=resp["public_ipaddr"],
            region=instance_offer.region,
            username="root",
            ssh_port=int(resp["ports"]["10022/tcp"][0]["HostPort"]),
            dockerized=False,
        )

    def terminate_instance(self, instance_id: str, region: str):
        self.api_client.destroy_instance(instance_id)
