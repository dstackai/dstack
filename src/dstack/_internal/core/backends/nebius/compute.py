import json
import re
import time
from typing import List, Optional

import dstack.version as version
from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import get_user_data
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.nebius.api_client import NebiusAPIClient
from dstack._internal.core.backends.nebius.config import NebiusConfig
from dstack._internal.core.backends.nebius.types import (
    ForbiddenError,
    NotFoundError,
    ResourcesSpec,
)
from dstack._internal.core.errors import NoCapacityError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run

MEGABYTE = 1024**2
INSTANCE_PULL_INTERVAL = 10


class NebiusCompute(Compute):
    def __init__(self, config: NebiusConfig):
        self.config = config
        self.api_client = NebiusAPIClient(json.loads(self.config.creds.data))

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.NEBIUS,
            locations=self.config.regions,
            requirements=requirements,
        )
        # TODO(egor-s) quotas
        return [
            InstanceOfferWithAvailability(
                **offer.dict(), availability=InstanceAvailability.UNKNOWN
            )
            for offer in offers
        ]

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        cuda = len(instance_offer.instance.resources.gpus) > 0
        security_group_id = self._get_security_group_id(project_name=run.project_name)
        subnet_id = self._get_subnet_id(zone=instance_offer.region)
        image_id = self._get_image_id(cuda=cuda)

        try:
            disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
            resp = self.api_client.compute_instances_create(
                folder_id=self.config.folder_id,
                name=job.job_spec.job_name,  # TODO(egor-s) make globally unique
                zone_id=instance_offer.region,
                platform_id=instance_offer.instance.name,
                resources_spec=ResourcesSpec(
                    memory=int(instance_offer.instance.resources.memory_mib * MEGABYTE),
                    cores=instance_offer.instance.resources.cpus,
                    coreFraction=100,
                    gpus=len(instance_offer.instance.resources.gpus),
                ),
                metadata={
                    "user-data": get_user_data(
                        backend=BackendType.NEBIUS,
                        image_name=job.job_spec.image_name,
                        authorized_keys=[
                            run.run_spec.ssh_key_pub.strip(),
                            project_ssh_public_key.strip(),
                        ],
                        registry_auth_required=job.job_spec.registry_auth is not None,
                    ),
                },
                disk_size_gb=disk_size,
                image_id=image_id,
                subnet_id=subnet_id,
                security_group_ids=[security_group_id],
                labels=self._get_labels(project=run.project_name),
            )
        except ForbiddenError as e:
            if instance_offer.instance.name in e.args[0]:
                raise NoCapacityError(json.loads(e.args[0])["message"])
            raise
        instance_id = resp["metadata"]["instanceId"]
        try:
            while True:
                instance = self.api_client.compute_instances_get(instance_id)
                if "primaryV4Address" in instance["networkInterfaces"][0]:
                    break
                time.sleep(INSTANCE_PULL_INTERVAL)
        except Exception:
            self.terminate_instance(instance_id, instance_offer.region)
            raise
        return LaunchedInstanceInfo(
            instance_id=instance_id,
            ip_address=instance["networkInterfaces"][0]["primaryV4Address"]["oneToOneNat"][
                "address"
            ],
            region=instance_offer.region,
            username="ubuntu",
            ssh_port=22,
            dockerized=True,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        try:
            self.api_client.compute_instances_delete(instance_id)
        except NotFoundError:
            pass

    def _get_security_group_id(self, project_name: str) -> str:
        name = project_name
        security_groups = self.api_client.vpc_security_groups_list(
            folder_id=self.config.folder_id,
            filter=f'name="{name}"',
        )
        if security_groups:
            return security_groups[0]["id"]
        resp = self.api_client.vpc_security_groups_create(
            folder_id=self.config.folder_id,
            name=name,
            network_id=self.config.network_id,
            rule_specs=[
                {
                    "description": "SSH access",
                    "direction": "INGRESS",
                    "ports": {"fromPort": 22, "toPort": 22},
                    "protocolName": "ANY",
                    "cidrBlocks": {"v4CidrBlocks": ["0.0.0.0/0"]},
                },
                {
                    "description": "Project intranet",
                    "direction": "INGRESS",
                    "protocolName": "ANY",
                    "predefinedTarget": "self_security_group",
                },
                {
                    "description": "Internet access",
                    "direction": "EGRESS",
                    "protocolName": "ANY",
                    "cidrBlocks": {"v4CidrBlocks": ["0.0.0.0/0"]},
                },
            ],
            description="For job instance, by dstack",
            labels=self._get_labels(project=project_name),
        )
        return resp["response"]["id"]

    def _get_subnet_id(self, zone: str, name: Optional[str] = None) -> str:
        name = name or f"default-{zone}"
        subnets = self.api_client.vpc_subnets_list(folder_id=self.config.folder_id)
        for subnet in subnets:
            if subnet["name"] == name:
                return subnet["id"]
        n = len(subnets)
        resp = self.api_client.vpc_subnets_create(
            folder_id=self.config.folder_id,
            name=name,
            network_id=self.config.network_id,
            zone=zone,
            cird_blocks=[f"10.{n}.0.0/16"],
            labels=self._get_labels(),
        )
        return resp["response"]["id"]

    def _get_image_id(self, cuda: bool) -> str:
        image_name = re.sub(r"[^a-z0-9-]", "-", f"dstack-{version.base_image}")
        if cuda:
            image_name += "-cuda"
        images = self.api_client.compute_images_list(
            folder_id="bjel82ie37qos4pc6guk", filter=f'name="{image_name}"'
        )
        return images[0]["id"]

    def _get_labels(self, **kwargs) -> dict:
        labels = {
            "owner": "dstack",
            **kwargs,
        }
        if version.__version__:
            labels["dstack-version"] = version.__version__.replace(".", "-")
        return labels
