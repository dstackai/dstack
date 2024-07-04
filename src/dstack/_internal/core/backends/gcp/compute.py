import concurrent.futures
import json
from collections import defaultdict
from typing import Callable, Dict, List, Optional

import google.api_core.exceptions
import google.cloud.compute_v1 as compute_v1
from google.cloud import tpu_v2

import dstack._internal.core.backends.gcp.auth as auth
import dstack._internal.core.backends.gcp.resources as gcp_resources
from dstack._internal.core.backends.base.compute import (
    Compute,
    get_gateway_user_data,
    get_instance_name,
    get_shim_commands,
    get_user_data,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.gcp.config import GCPConfig
from dstack._internal.core.errors import (
    ComputeError,
    ComputeResourceNotFoundError,
    NoCapacityError,
    ProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import (
    GatewayComputeConfiguration,
    GatewayProvisioningData,
)
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
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
        self.routers_client = compute_v1.RoutersClient(credentials=self.credentials)
        self.tpu_client = tpu_v2.TpuClient(credentials=self.credentials)

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
            # todo quotas: cpu, memory, global gpu, tpu
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
        is_tpu = False
        if backend_data is not None:
            backend_data_dict = json.loads(backend_data)
            zone = backend_data_dict["zone"]
            is_tpu = backend_data_dict.get("is_tpu", False)
        try:
            if is_tpu:
                name = f"projects/{self.project_id}/locations/{zone}/nodes/{instance_id}"
                delete_request = tpu_v2.DeleteNodeRequest(
                    name=name,
                )
                self.tpu_client.delete_node(request=delete_request)
            else:
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
        allocate_public_ip = self.config.allocate_public_ips
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
        tpu = (
            _is_tpu(instance_offer.instance.resources.gpus[0].name)
            if instance_offer.instance.resources.gpus
            else False
        )
        if tpu:
            instance_id = f"tpu-{instance_config.instance_name}"
            startup_script = _get_tpu_startup_script(authorized_keys)
            for zone in _get_instance_zones(instance_offer):
                tpu_node = gcp_resources.create_tpu_node_struct(
                    instance_name=instance_offer.instance.name,
                    startup_script=startup_script,
                    authorized_keys=authorized_keys,
                    spot=instance_offer.instance.resources.spot,
                    labels=labels,
                    subnetwork=subnetwork,
                    allocate_public_ip=allocate_public_ip,
                )
                create_node_request = tpu_v2.CreateNodeRequest(
                    parent=f"projects/{self.config.project_id}/locations/{zone}",
                    node_id=instance_id,
                    node=tpu_node,
                )
                try:
                    # GCP needs some time to return an error in case of no capacity (< 30s).
                    # Call wait_for_operation() to get the capacity error and try another option.
                    # If the request succeeds, we'll probably timeout and update_provisioning_data() will get hostname.
                    operation = self.tpu_client.create_node(request=create_node_request)
                    gcp_resources.wait_for_operation(operation, timeout=30)
                except (
                    google.api_core.exceptions.ServiceUnavailable,
                    google.api_core.exceptions.NotFound,
                    google.api_core.exceptions.ResourceExhausted,
                ) as e:
                    logger.debug("Got GCP error when provisioning a TPU: %s", e)
                    continue
                except concurrent.futures.TimeoutError:
                    pass
                return JobProvisioningData(
                    backend=instance_offer.backend,
                    instance_type=instance_offer.instance,
                    instance_id=instance_id,
                    hostname=None,
                    internal_ip=None,
                    region=instance_offer.region,
                    availability_zone=zone,
                    price=instance_offer.price,
                    ssh_port=22,
                    username="ubuntu",
                    ssh_proxy=None,
                    dockerized=True,
                    backend_data=json.dumps({"is_tpu": tpu, "zone": zone}),
                )
            raise NoCapacityError()

        if not allocate_public_ip and not gcp_resources.has_vpc_nat_access(
            routers_client=self.routers_client,
            project_id=self.config.vpc_project_id or self.config.project_id,
            vpc_name=self.config.vpc_resource_name,
            region=instance_offer.region,
        ):
            raise ComputeError(
                "VPC does not have access to the external internet through Cloud NAT. "
                f"Region: {instance_offer.region}, VPC name: {self.config.vpc_resource_name}, "
                f"Project ID: {self.config.vpc_project_id or self.config.project_id}."
            )

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
                allocate_public_ip=allocate_public_ip,
            )
            try:
                # GCP needs some time to return an error in case of no capacity (< 30s).
                # Call wait_for_operation() to get the capacity error and try another option.
                # If the request succeeds, we'll probably timeout and update_provisioning_data() will get hostname.
                operation = self.instances_client.insert(request=request)
                gcp_resources.wait_for_extended_operation(operation, timeout=30)
            except (
                google.api_core.exceptions.ServiceUnavailable,
                google.api_core.exceptions.NotFound,
            ) as e:
                logger.debug("Got GCP error when provisioning a VM: %s", e)
                continue
            except concurrent.futures.TimeoutError:
                pass
            return JobProvisioningData(
                backend=instance_offer.backend,
                instance_type=instance_offer.instance,
                instance_id=instance_name,
                public_ip_enabled=allocate_public_ip,
                hostname=None,
                internal_ip=None,
                region=instance_offer.region,
                availability_zone=zone,
                price=instance_offer.price,
                username="ubuntu",
                ssh_port=22,
                dockerized=True,
                ssh_proxy=None,
                backend_data=json.dumps({"zone": zone}),
            )
        raise NoCapacityError()

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        allocate_public_ip = self.config.allocate_public_ips
        zone = provisioning_data.region
        is_tpu = False
        if provisioning_data.backend_data is not None:
            backend_data_dict = json.loads(provisioning_data.backend_data)
            zone = backend_data_dict["zone"]
            is_tpu = backend_data_dict.get("is_tpu", False)

        if is_tpu:
            node_request = tpu_v2.GetNodeRequest(
                name=f"projects/dstack/locations/{zone}/nodes/{provisioning_data.instance_id}",
            )
            try:
                instance = self.tpu_client.get_node(request=node_request)
            except google.api_core.exceptions.NotFound:
                raise ProvisioningError("Failed to get instance IP address. Instance not found.")

            # See states https://cloud.google.com/python/docs/reference/tpu/latest/google.cloud.tpu_v2.types.Node.State
            if instance.state in [0, 1]:
                return
            if instance.state == 2:
                if allocate_public_ip:
                    hostname = instance.network_endpoints[0].access_config.external_ip
                else:
                    hostname = instance.network_endpoints[0].ip_address
                provisioning_data.hostname = hostname
                provisioning_data.internal_ip = instance.network_endpoints[0].ip_address
                return
            raise ProvisioningError(
                f"Failed to get instance IP address. Instance state: {instance.state}"
            )

        try:
            instance = self.instances_client.get(
                project=self.config.project_id, zone=zone, instance=provisioning_data.instance_id
            )
        except google.api_core.exceptions.NotFound:
            raise ProvisioningError("Failed to get instance IP address. Instance not found.")

        if instance.status in ["PROVISIONING", "STAGING"]:
            return
        if instance.status == "RUNNING":
            if allocate_public_ip:
                hostname = instance.network_interfaces[0].access_configs[0].nat_i_p
            else:
                hostname = instance.network_interfaces[0].network_i_p
            provisioning_data.hostname = hostname
            provisioning_data.internal_ip = instance.network_interfaces[0].network_i_p
            return
        raise ProvisioningError(
            f"Failed to get instance IP address. Instance status: {instance.status}"
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
                SSHKey(public=project_ssh_public_key.strip()),
            ],
            job_docker_config=None,
            user=run.user,
        )
        return self.create_instance(instance_offer, instance_config)

    def create_gateway(
        self,
        configuration: GatewayComputeConfiguration,
    ) -> GatewayProvisioningData:
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
        return GatewayProvisioningData(
            instance_id=configuration.instance_name,
            region=configuration.region,  # used for instance termination
            availability_zone=zone,
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
        # remove TPU Pod for initial release
        if _is_tpu(f"tpu-{offer.instance.name}") and _is_pod(offer.instance.name):
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
    if _is_tpu(gpu.name):
        return True
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


def _get_tpu_startup_script(authorized_keys: List[str]) -> str:
    commands = get_shim_commands(
        authorized_keys=authorized_keys, is_privileged=True, pjrt_device="TPU"
    )
    startup_script = " ".join([" && ".join(commands)])
    startup_script = "#! /bin/bash\n" + startup_script
    return startup_script


def _is_tpu(name: str) -> bool:
    tpu_versions = ["tpu-v2", "tpu-v3", "tpu-v4", "tpu-v5p", "tpu-v5litepod"]
    parts = name.split("-")
    if len(parts) == 3:
        version = f"{parts[0]}-{parts[1]}"
        cores = parts[2]
        if version in tpu_versions and cores.isdigit():
            return True
    return False


def _is_pod(instance_name: str) -> bool:
    parts = instance_name.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid tpu type: {instance_name}")
    version, tensor_cores = parts
    try:
        tensor_cores = int(tensor_cores)
    except ValueError:
        raise ValueError(f"Invalid number in tpu tensor cores: {tensor_cores}")
    if version in ["v2", "v3", "v5p", "v5litepod"]:
        return tensor_cores > 8
    elif version == "v4":
        return True
    else:
        raise ValueError(f"Unknown TPU version: {version}")
