from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

import google.api_core.exceptions
import google.cloud.compute_v1 as compute_v1

import dstack._internal.core.backends.gcp.auth as auth
import dstack._internal.core.backends.gcp.resources as gcp_resources
from dstack._internal.core.backends.base.compute import (
    Compute,
    get_gateway_user_data,
    get_user_data,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.gcp.config import GCPConfig
from dstack._internal.core.errors import NoCapacityError, ResourceNotFoundError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedGatewayInfo,
    LaunchedInstanceInfo,
    Resources,
)
from dstack._internal.core.models.runs import Job, Requirements, Run


class GCPCompute(Compute):
    def __init__(self, config: GCPConfig):
        self.config = config
        self.credentials, self.project_id = auth.authenticate(config.creds)
        self.instances_client = compute_v1.InstancesClient(credentials=self.credentials)
        self.firewalls_client = compute_v1.FirewallsClient(credentials=self.credentials)
        self.regions_client = compute_v1.RegionsClient(credentials=self.credentials)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            provider=BackendType.GCP.value,
            requirements=requirements,
            extra_filter=_supported_instances_and_zones(self.config.regions),
        )
        quotas = defaultdict(dict)
        for region in self.regions_client.list(project=self.config.project_id):
            for quota in region.quotas:
                quotas[region.name][quota.metric] = quota.limit - quota.usage
        offers_with_availability: Dict[Tuple[str, str], InstanceOfferWithAvailability] = {}
        for offer in offers:
            key = (
                _unique_instance_name(offer.instance),
                offer.region[:-2],  # strip zone
            )
            if key in offers_with_availability:
                continue
            availability = InstanceAvailability.UNKNOWN
            if not _has_gpu_quota(quotas[offer.region], offer.instance.resources):
                availability = InstanceAvailability.NO_QUOTA
            # todo quotas: cpu, memory, global gpu

            offers_with_availability[key] = InstanceOfferWithAvailability(
                **offer.dict(), availability=availability
            )
            offers_with_availability[key].region = offer.region[:-2]  # strip zone
        return list(offers_with_availability.values())

    def terminate_instance(self, instance_id: str, region: str):
        try:
            self.instances_client.delete(
                project=self.config.project_id, zone=region, instance=instance_id
            )
        except google.api_core.exceptions.NotFound:
            pass

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
    ) -> LaunchedInstanceInfo:
        project_id = run.project_name
        instance_name = run.run_spec.run_name
        gcp_resources.create_runner_firewall_rules(
            firewalls_client=self.firewalls_client,
            project_id=self.config.project_id,
        )
        for zone in _get_instance_zones(instance_offer):
            request = compute_v1.InsertInstanceRequest()
            request.zone = zone
            request.project = self.config.project_id
            request.instance_resource = gcp_resources.create_instance_struct(
                disk_size=100,
                image_id=gcp_resources.get_image_id(
                    len(instance_offer.instance.resources.gpus) > 0,
                ),
                machine_type=instance_offer.instance.name,
                accelerators=gcp_resources.get_accelerators(
                    project_id=self.config.project_id,
                    zone=zone,
                    gpus=instance_offer.instance.resources.gpus,
                ),
                spot=instance_offer.instance.resources.spot,
                user_data=get_user_data(
                    backend=BackendType.GCP,
                    image_name=job.job_spec.image_name,
                    authorized_keys=[
                        run.run_spec.ssh_key_pub.strip(),
                        project_ssh_public_key.strip(),
                    ],
                ),
                labels={
                    "owner": "dstack",
                    "dstack_project": project_id,
                    "dstack_user": run.user,
                },
                tags=[gcp_resources.DSTACK_INSTANCE_TAG],
                instance_name=instance_name,
                zone=zone,
                service_account=self.config.service_account_email,
            )
            try:
                operation = self.instances_client.insert(request=request)
                gcp_resources.wait_for_extended_operation(operation, "instance creation")
            except (
                google.api_core.exceptions.ServiceUnavailable,
                google.api_core.exceptions.NotFound,
            ):
                continue
            instance = self.instances_client.get(
                project=self.config.project_id, zone=zone, instance=instance_name
            )
            return LaunchedInstanceInfo(
                instance_id=instance_name,
                region=zone,
                ip_address=instance.network_interfaces[0].access_configs[0].nat_i_p,
                username="ubuntu",
                ssh_port=22,
                dockerized=True,
            )
        raise NoCapacityError()

    def create_gateway(
        self,
        instance_name: str,
        ssh_key_pub: str,
        region: str,
        project_id: str,
    ) -> LaunchedGatewayInfo:
        gcp_resources.create_gateway_firewall_rules(
            firewalls_client=self.firewalls_client,
            project_id=self.config.project_id,
        )
        # e2-micro is available in every zone
        for i in self.regions_client.list(project=self.config.project_id):
            if i.name == region:
                zone = i.zones[0].split("/")[-1]
                break
        else:
            raise ResourceNotFoundError()

        request = compute_v1.InsertInstanceRequest()
        request.zone = zone
        request.project = self.config.project_id
        request.instance_resource = gcp_resources.create_instance_struct(
            disk_size=10,
            image_id=gcp_resources.get_gateway_image_id(),
            machine_type="e2-micro",
            accelerators=[],
            spot=False,
            user_data=get_gateway_user_data(ssh_key_pub),
            labels={
                "owner": "dstack",
                "dstack_project": project_id,
            },
            tags=[gcp_resources.DSTACK_GATEWAY_TAG],
            instance_name=instance_name,
            zone=zone,
            service_account=None,
        )
        operation = self.instances_client.insert(request=request)
        gcp_resources.wait_for_extended_operation(operation, "instance creation")
        instance = self.instances_client.get(
            project=self.config.project_id, zone=zone, instance=instance_name
        )
        return LaunchedGatewayInfo(
            instance_id=instance_name,
            region=zone,  # used for instance termination
            ip_address=instance.network_interfaces[0].access_configs[0].nat_i_p,
        )


def _supported_instances_and_zones(
    regions: List[str],
) -> Optional[Callable[[InstanceOffer], bool]]:
    regions = set(regions)

    def _filter(offer: InstanceOffer) -> bool:
        # strip zone
        if offer.region[:-2] not in regions:
            return False
        for family in [
            "e2-medium",
            "e2-standard-",
            "e2-highmem-",
            "e2-highcpu-",
            "m1-",
            "a2-",
            "g2-",
        ]:
            if offer.instance.name.startswith(family):
                return True
        if offer.instance.resources.gpus:
            if offer.instance.resources.gpus[0].name not in {"K80", "P4"}:
                return True
        return False

    return _filter


def _has_gpu_quota(quotas: Dict[str, int], resources: Resources) -> bool:
    if not resources.gpus:
        return True
    gpu = resources.gpus[0]
    quota_name = f"NVIDIA_{gpu.name}_GPUS"
    if gpu.name == "A100" and gpu.memory_mib == 80 * 1024:
        quota_name = "NVIDIA_A100_80GB_GPUS"
    if resources.spot:
        quota_name = "PREEMPTIBLE_" + quota_name
    return len(resources.gpus) <= quotas.get(quota_name, 0)


def _unique_instance_name(instance: InstanceType) -> str:
    if instance.resources.spot:
        name = f"{instance.name}-spot"
    else:
        name = instance.name
    if not instance.resources.gpus:
        return name
    gpu = instance.resources.gpus[0]
    return f"{name}-{gpu.name}-{gpu.memory_mib}"


def _get_instance_zones(instance_offer: InstanceOffer) -> List[str]:
    zones = []
    for offer in get_catalog_offers(provider=BackendType.GCP.value):
        if _unique_instance_name(instance_offer.instance) != _unique_instance_name(offer.instance):
            continue
        if offer.region[:-2] != instance_offer.region:
            continue
        zones.append(offer.region)
    return zones
