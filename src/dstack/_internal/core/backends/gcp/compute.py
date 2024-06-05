import json
from collections import defaultdict
from typing import Callable, Dict, List, Optional

import google.api_core.exceptions
import google.cloud.compute_v1 as compute_v1

import dstack._internal.core.backends.gcp.auth as auth
import dstack._internal.core.backends.gcp.resources as gcp_resources
from dstack._internal.core.backends.base.compute import (
    Compute,
    get_gateway_user_data,
    get_instance_name,
    get_user_data,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.gcp.config import GCPConfig
from dstack._internal.core.errors import (
    ComputeResourceNotFoundError,
    NoCapacityError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import GatewayComputeConfiguration
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedGatewayInfo,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class GCPCompute(Compute):
    def __init__(self, config: GCPConfig):
        self.config = config
        self.credentials, self.project_id = auth.authenticate(config.creds)
        self.instances_client = compute_v1.InstancesClient(credentials=self.credentials)
        self.firewalls_client = compute_v1.FirewallsClient(credentials=self.credentials)
        self.regions_client = compute_v1.RegionsClient(credentials=self.credentials)
        self.subnetworks_client = compute_v1.SubnetworksClient(credentials=self.credentials)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.GCP,
            requirements=requirements,
            extra_filter=_supported_instances_and_zones(self.config.regions),
        )
        quotas: Dict[str, Dict[str, float]] = defaultdict(dict)
        for region in self.regions_client.list(project=self.config.project_id):
            for quota in region.quotas:
                quotas[region.name][quota.metric] = quota.limit - quota.usage

        seen_region_offers = set()
        offers_with_availability = []
        for offer in offers:
            region = offer.region[:-2]  # strip zone
            key = (_unique_instance_name(offer.instance), region)
            if key in seen_region_offers:
                continue
            seen_region_offers.add(key)
            availability = InstanceAvailability.NO_QUOTA
            if _has_gpu_quota(quotas[region], offer.instance.resources):
                availability = InstanceAvailability.UNKNOWN
            # todo quotas: cpu, memory, global gpu
            offers_with_availability.append(
                InstanceOfferWithAvailability(**offer.dict(), availability=availability)
            )
            offers_with_availability[-1].region = region

        return offers_with_availability

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        # Old instances have region set to zone, e.g. us-central1-a.
        # New instance have region set to region, e.g. us-central1. Zone is stored in backend_data.
        zone = region
        if backend_data is not None:
            backend_data_dict = json.loads(backend_data)
            zone = backend_data_dict["zone"]
        try:
            self.instances_client.delete(
                project=self.config.project_id, zone=zone, instance=instance_id
            )
        except google.api_core.exceptions.NotFound:
            pass

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> JobProvisioningData:
        instance_name = instance_config.instance_name
        if not gcp_resources.is_valid_resource_name(instance_name):
            # In a rare case the instance name is invalid in GCP,
            # we better use a random instance name than fail provisioning.
            instance_name = gcp_resources.generate_random_resource_name()
            logger.warning(
                "Invalid GCP instance name: %s. A new valid name is generated: %s",
                instance_config.instance_name,
                instance_name,
            )

        authorized_keys = instance_config.get_public_keys()

        # If a shared VPC is not used, we can create firewall rules for user
        if self.config.vpc_project_id is None:
            gcp_resources.create_runner_firewall_rules(
                firewalls_client=self.firewalls_client,
                project_id=self.config.project_id,
                network=self.config.vpc_resource_name,
            )
        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)

        # Choose any usable subnet in a VPC.
        # Configuring a specific subnet per region is not supported yet.
        subnetwork = _get_vpc_subnet(
            subnetworks_client=self.subnetworks_client,
            config=self.config,
            region=instance_offer.region,
        )

        labels = {
            "owner": "dstack",
            "dstack_project": instance_config.project_name.lower(),
            "dstack_user": instance_config.user.lower(),
        }
        labels = {k: v for k, v in labels.items() if gcp_resources.is_valid_label_value(v)}

        for zone in _get_instance_zones(instance_offer):
            request = compute_v1.InsertInstanceRequest()
            request.zone = zone
            request.project = self.config.project_id
            request.instance_resource = gcp_resources.create_instance_struct(
                disk_size=disk_size,
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
                user_data=get_user_data(authorized_keys),
                authorized_keys=authorized_keys,
                labels=labels,
                tags=[gcp_resources.DSTACK_INSTANCE_TAG],
                instance_name=instance_name,
                zone=zone,
                network=self.config.vpc_resource_name,
                subnetwork=subnetwork,
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
            return JobProvisioningData(
                backend=instance_offer.backend,
                instance_type=instance_offer.instance,
                instance_id=instance_name,
                hostname=instance.network_interfaces[0].access_configs[0].nat_i_p,
                internal_ip=instance.network_interfaces[0].network_i_p,
                region=instance_offer.region,
                price=instance_offer.price,
                username="ubuntu",
                ssh_port=22,
                dockerized=True,
                ssh_proxy=None,
                backend_data=json.dumps({"zone": zone}),
            )
        raise NoCapacityError()

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
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

    def create_gateway(
        self,
        configuration: GatewayComputeConfiguration,
    ) -> LaunchedGatewayInfo:
        if self.config.vpc_project_id is None:
            gcp_resources.create_gateway_firewall_rules(
                firewalls_client=self.firewalls_client,
                project_id=self.config.project_id,
                network=self.config.vpc_resource_name,
            )
        for i in self.regions_client.list(project=self.config.project_id):
            if i.name == configuration.region:
                zone = i.zones[0].split("/")[-1]
                break
        else:
            raise ComputeResourceNotFoundError()

        # Choose any usable subnet in a VPC.
        # Configuring a specific subnet per region is not supported yet.
        subnetwork = _get_vpc_subnet(
            subnetworks_client=self.subnetworks_client,
            config=self.config,
            region=configuration.region,
        )

        request = compute_v1.InsertInstanceRequest()
        request.zone = zone
        request.project = self.config.project_id
        request.instance_resource = gcp_resources.create_instance_struct(
            disk_size=10,
            image_id=gcp_resources.get_gateway_image_id(),
            machine_type="e2-small",
            accelerators=[],
            spot=False,
            user_data=get_gateway_user_data(configuration.ssh_key_pub),
            authorized_keys=[configuration.ssh_key_pub],
            labels={
                "owner": "dstack",
                "dstack_project": configuration.project_name,
            },
            tags=[gcp_resources.DSTACK_GATEWAY_TAG],
            instance_name=configuration.instance_name,
            zone=zone,
            service_account=None,
            network=self.config.vpc_resource_name,
            subnetwork=subnetwork,
        )
        operation = self.instances_client.insert(request=request)
        gcp_resources.wait_for_extended_operation(operation, "instance creation")
        instance = self.instances_client.get(
            project=self.config.project_id, zone=zone, instance=configuration.instance_name
        )
        return LaunchedGatewayInfo(
            instance_id=configuration.instance_name,
            region=configuration.region,  # used for instance termination
            ip_address=instance.network_interfaces[0].access_configs[0].nat_i_p,
            backend_data=json.dumps({"zone": zone}),
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


def _get_vpc_subnet(
    subnetworks_client: compute_v1.SubnetworksClient,
    config: GCPConfig,
    region: str,
) -> Optional[str]:
    if config.vpc_name is None:
        return None
    return gcp_resources.get_vpc_subnet_or_error(
        subnetworks_client=subnetworks_client,
        vpc_project_id=config.vpc_project_id or config.project_id,
        vpc_name=config.vpc_name,
        region=region,
    )


def _supported_instances_and_zones(
    regions: List[str],
) -> Optional[Callable[[InstanceOffer], bool]]:
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


def _has_gpu_quota(quotas: Dict[str, float], resources: Resources) -> bool:
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
    for offer in get_catalog_offers(backend=BackendType.GCP):
        if _unique_instance_name(instance_offer.instance) != _unique_instance_name(offer.instance):
            continue
        if offer.region[:-2] != instance_offer.region:
            continue
        zones.append(offer.region)
    return zones
