import concurrent.futures
import json
import threading
from collections import defaultdict
from typing import Callable, Dict, List, Literal, Optional, Tuple

import google.api_core.exceptions
import google.cloud.compute_v1 as compute_v1
from cachetools import TTLCache, cachedmethod
from google.cloud import tpu_v2
from google.cloud.compute_v1.types.compute import Instance
from gpuhunt import KNOWN_TPUS

import dstack._internal.core.backends.gcp.auth as auth
import dstack._internal.core.backends.gcp.resources as gcp_resources
from dstack import version
from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithCreateInstanceSupport,
    ComputeWithGatewaySupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithPrivateGatewaySupport,
    ComputeWithVolumeSupport,
    generate_unique_gateway_instance_name,
    generate_unique_instance_name,
    generate_unique_volume_name,
    get_gateway_user_data,
    get_shim_commands,
    get_user_data,
    merge_tags,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.gcp.features import tcpx as tcpx_features
from dstack._internal.core.backends.gcp.models import GCPConfig
from dstack._internal.core.errors import (
    ComputeError,
    ComputeResourceNotFoundError,
    NoCapacityError,
    PlacementGroupInUseError,
    ProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
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
)
from dstack._internal.core.models.placement import PlacementGroup, PlacementGroupProvisioningData
from dstack._internal.core.models.resources import Memory, Range
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.core.models.volumes import (
    Volume,
    VolumeAttachmentData,
    VolumeProvisioningData,
)
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# pd-balanced disks can be 10GB-64TB, but dstack images are 20GB and cannot grow larger
# than 32TB because of filesystem settings
CONFIGURABLE_DISK_SIZE = Range[Memory](min=Memory.parse("20GB"), max=Memory.parse("32TB"))


TPU_VERSIONS = [tpu.name for tpu in KNOWN_TPUS]


class GCPVolumeDiskBackendData(CoreModel):
    type: Literal["disk"] = "disk"
    disk_type: str


class GCPCompute(
    ComputeWithCreateInstanceSupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithGatewaySupport,
    ComputeWithPrivateGatewaySupport,
    ComputeWithVolumeSupport,
    Compute,
):
    def __init__(self, config: GCPConfig):
        super().__init__()
        self.config = config
        self.credentials, _ = auth.authenticate(config.creds, self.config.project_id)
        self.instances_client = compute_v1.InstancesClient(credentials=self.credentials)
        self.firewalls_client = compute_v1.FirewallsClient(credentials=self.credentials)
        self.regions_client = compute_v1.RegionsClient(credentials=self.credentials)
        self.subnetworks_client = compute_v1.SubnetworksClient(credentials=self.credentials)
        self.routers_client = compute_v1.RoutersClient(credentials=self.credentials)
        self.tpu_client = tpu_v2.TpuClient(credentials=self.credentials)
        self.disk_client = compute_v1.DisksClient(credentials=self.credentials)
        self.resource_policies_client = compute_v1.ResourcePoliciesClient(
            credentials=self.credentials
        )
        self._extra_subnets_cache_lock = threading.Lock()
        self._extra_subnets_cache = TTLCache(maxsize=30, ttl=60)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        regions = get_or_error(self.config.regions)
        offers = get_catalog_offers(
            backend=BackendType.GCP,
            requirements=requirements,
            configurable_disk_size=CONFIGURABLE_DISK_SIZE,
            extra_filter=_supported_instances_and_zones(regions),
        )
        quotas: Dict[str, Dict[str, float]] = defaultdict(dict)
        for region in self.regions_client.list(project=self.config.project_id):
            for quota in region.quotas:
                quotas[region.name][quota.metric] = quota.limit - quota.usage

        offer_keys_to_offers = {}
        offers_with_availability = []
        for offer in offers:
            region = offer.region[:-2]  # strip zone
            key = (_unique_instance_name(offer.instance), region)
            if key in offer_keys_to_offers:
                offer_keys_to_offers[key].availability_zones.append(offer.region)
                continue
            availability = InstanceAvailability.NO_QUOTA
            if _has_gpu_quota(quotas[region], offer.instance.resources):
                availability = InstanceAvailability.UNKNOWN
            # todo quotas: cpu, memory, global gpu, tpu
            offer_with_availability = InstanceOfferWithAvailability(
                **offer.dict(),
                availability=availability,
                availability_zones=[offer.region],
            )
            offer_keys_to_offers[key] = offer_with_availability
            offers_with_availability.append(offer_with_availability)
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
                name = f"projects/{self.config.project_id}/locations/{zone}/nodes/{instance_id}"
                delete_request = tpu_v2.DeleteNodeRequest(name=name)
                self.tpu_client.delete_node(request=delete_request)
            else:
                self.instances_client.delete(
                    project=self.config.project_id,
                    zone=zone,
                    instance=instance_id,
                )
        except google.api_core.exceptions.NotFound:
            pass

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name(
            instance_config, max_length=gcp_resources.MAX_RESOURCE_NAME_LEN
        )
        allocate_public_ip = self.config.allocate_public_ips
        authorized_keys = instance_config.get_public_keys()

        # get_offers always fills instance_offer.availability_zones
        zones = get_or_error(instance_offer.availability_zones)
        if len(zones) == 0:
            raise NoCapacityError("No eligible availability zones")
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
        extra_subnets = self._get_extra_subnets(
            region=instance_offer.region,
            instance_type_name=instance_offer.instance.name,
        )
        placement_policy = None
        if placement_group is not None:
            placement_policy = gcp_resources.get_placement_policy_resource_name(
                project_id=self.config.project_id,
                region=instance_offer.region,
                placement_policy=placement_group.name,
            )
        labels = {
            "owner": "dstack",
            "dstack_project": instance_config.project_name.lower(),
            "dstack_name": instance_config.instance_name,
            "dstack_user": instance_config.user.lower(),
        }
        labels = merge_tags(
            base_tags=labels,
            backend_tags=self.config.tags,
            resource_tags=instance_config.tags,
        )
        labels = gcp_resources.filter_invalid_labels(labels)
        is_tpu = (
            _is_tpu(instance_offer.instance.resources.gpus[0].name)
            if instance_offer.instance.resources.gpus
            else False
        )
        if is_tpu:
            instance_id = instance_name
            startup_script = _get_tpu_startup_script(authorized_keys)
            # GCP does not allow attaching disks while TPUs is creating,
            # so we need to attach the disks on creation.
            data_disks = _get_tpu_data_disks(self.config.project_id, instance_config.volumes)
            for zone in zones:
                tpu_node = gcp_resources.create_tpu_node_struct(
                    instance_name=instance_offer.instance.name,
                    startup_script=startup_script,
                    authorized_keys=authorized_keys,
                    spot=instance_offer.instance.resources.spot,
                    labels=labels,
                    runtime_version=_get_tpu_runtime_version(instance_offer.instance.name),
                    network=self.config.vpc_resource_name,
                    subnetwork=subnetwork,
                    allocate_public_ip=allocate_public_ip,
                    service_account=self.config.vm_service_account,
                    data_disks=data_disks,
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
                    backend_data=json.dumps({"is_tpu": is_tpu, "zone": zone}),
                )
            raise NoCapacityError()

        for zone in zones:
            request = compute_v1.InsertInstanceRequest()
            request.zone = zone
            request.project = self.config.project_id
            request.instance_resource = gcp_resources.create_instance_struct(
                disk_size=disk_size,
                image_id=_get_image_id(
                    instance_type_name=instance_offer.instance.name,
                    cuda=len(instance_offer.instance.resources.gpus) > 0,
                ),
                machine_type=instance_offer.instance.name,
                accelerators=gcp_resources.get_accelerators(
                    project_id=self.config.project_id,
                    zone=zone,
                    gpus=instance_offer.instance.resources.gpus,
                ),
                spot=instance_offer.instance.resources.spot,
                user_data=_get_user_data(
                    authorized_keys=authorized_keys,
                    instance_type_name=instance_offer.instance.name,
                ),
                authorized_keys=authorized_keys,
                labels=labels,
                tags=[gcp_resources.DSTACK_INSTANCE_TAG],
                instance_name=instance_name,
                zone=zone,
                service_account=self.config.vm_service_account,
                network=self.config.vpc_resource_name,
                subnetwork=subnetwork,
                extra_subnetworks=extra_subnets,
                allocate_public_ip=allocate_public_ip,
                placement_policy=placement_policy,
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
                name=f"projects/{self.config.project_id}/locations/{zone}/nodes/{provisioning_data.instance_id}",
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
            provisioning_data.hostname = _get_instance_ip(instance, allocate_public_ip)
            provisioning_data.internal_ip = instance.network_interfaces[0].network_i_p
            return
        raise ProvisioningError(
            f"Failed to get instance IP address. Instance status: {instance.status}"
        )

    def create_placement_group(
        self,
        placement_group: PlacementGroup,
        master_instance_offer: InstanceOffer,
    ) -> PlacementGroupProvisioningData:
        policy = compute_v1.ResourcePolicy(
            name=placement_group.name,
            region=placement_group.configuration.region,
            group_placement_policy=compute_v1.ResourcePolicyGroupPlacementPolicy(
                availability_domain_count=1,
                collocation="COLLOCATED",
            ),
        )
        self.resource_policies_client.insert(
            project=self.config.project_id,
            region=placement_group.configuration.region,
            resource_policy_resource=policy,
        )
        return PlacementGroupProvisioningData(backend=BackendType.GCP)

    def delete_placement_group(
        self,
        placement_group: PlacementGroup,
    ):
        try:
            operation = self.resource_policies_client.delete(
                project=self.config.project_id,
                region=placement_group.configuration.region,
                resource_policy=placement_group.name,
            )
            operation.result()  # Wait for operation to complete
        except google.api_core.exceptions.NotFound:
            logger.debug("Placement group %s not found", placement_group.name)
        except google.api_core.exceptions.BadRequest as e:
            if "is already being used by" in e.message:
                raise PlacementGroupInUseError()
            raise

    def is_suitable_placement_group(
        self,
        placement_group: PlacementGroup,
        instance_offer: InstanceOffer,
    ) -> bool:
        return placement_group.configuration.region == instance_offer.region

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

        instance_name = generate_unique_gateway_instance_name(
            configuration, max_length=gcp_resources.MAX_RESOURCE_NAME_LEN
        )
        # Choose any usable subnet in a VPC.
        # Configuring a specific subnet per region is not supported yet.
        subnetwork = _get_vpc_subnet(
            subnetworks_client=self.subnetworks_client,
            config=self.config,
            region=configuration.region,
        )

        labels = {
            "owner": "dstack",
            "dstack_project": configuration.project_name.lower(),
            "dstack_name": configuration.instance_name,
        }
        labels = merge_tags(
            base_tags=labels,
            backend_tags=self.config.tags,
            resource_tags=configuration.tags,
        )
        labels = gcp_resources.filter_invalid_labels(labels)

        request = compute_v1.InsertInstanceRequest()
        request.zone = zone
        request.project = self.config.project_id
        request.instance_resource = gcp_resources.create_instance_struct(
            disk_size=10,
            image_id=_get_gateway_image_id(),
            machine_type="e2-medium",
            accelerators=[],
            spot=False,
            user_data=get_gateway_user_data(configuration.ssh_key_pub),
            authorized_keys=[configuration.ssh_key_pub],
            labels=labels,
            tags=[gcp_resources.DSTACK_GATEWAY_TAG],
            instance_name=instance_name,
            zone=zone,
            service_account=self.config.vm_service_account,
            network=self.config.vpc_resource_name,
            subnetwork=subnetwork,
            allocate_public_ip=configuration.public_ip,
        )
        operation = self.instances_client.insert(request=request)
        gcp_resources.wait_for_extended_operation(operation, "instance creation")
        instance = self.instances_client.get(
            project=self.config.project_id, zone=zone, instance=instance_name
        )
        return GatewayProvisioningData(
            instance_id=instance_name,
            region=configuration.region,  # used for instance termination
            availability_zone=zone,
            ip_address=_get_instance_ip(instance, configuration.public_ip),
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

    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        logger.debug("Requesting persistent disk %s", volume.configuration.volume_id)
        zones = gcp_resources.get_availability_zones(
            regions_client=self.regions_client,
            project_id=self.config.project_id,
            region=volume.configuration.region,
        )
        for zone in zones:
            try:
                disk = self.disk_client.get(
                    project=self.config.project_id,
                    zone=zone,
                    disk=volume.configuration.volume_id,
                )
            except google.api_core.exceptions.NotFound:
                pass
            else:
                logger.debug("Found persistent disk %s", volume.configuration.volume_id)
                return VolumeProvisioningData(
                    backend=BackendType.GCP,
                    volume_id=disk.name,
                    size_gb=disk.size_gb,
                    availability_zone=zone,
                    attachable=True,
                    detachable=True,
                    backend_data=GCPVolumeDiskBackendData(
                        disk_type=gcp_resources.full_resource_name_to_name(disk.type_),
                    ).json(),
                )
        raise ComputeError(f"Persistent disk {volume.configuration.volume_id} not found")

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        zones = gcp_resources.get_availability_zones(
            regions_client=self.regions_client,
            project_id=self.config.project_id,
            region=volume.configuration.region,
        )
        if volume.configuration.availability_zone is not None:
            zones = [z for z in zones if z == volume.configuration.availability_zone]
        if len(zones) == 0:
            raise ComputeError(
                f"Failed to find availability zone in region {volume.configuration.region}"
            )
        zone = zones[0]

        disk_name = generate_unique_volume_name(
            volume, max_length=gcp_resources.MAX_RESOURCE_NAME_LEN
        )

        labels = {
            "owner": "dstack",
            "dstack_project": volume.project_name.lower(),
            "dstack_name": volume.name,
            "dstack_user": volume.user,
        }
        labels = merge_tags(
            base_tags=labels,
            backend_tags=self.config.tags,
            resource_tags=volume.configuration.tags,
        )
        labels = gcp_resources.filter_invalid_labels(labels)

        disk = compute_v1.Disk()
        disk.name = disk_name
        disk.size_gb = volume.configuration.size_gb
        disk.type_ = f"zones/{zone}/diskTypes/pd-balanced"
        disk.labels = labels

        logger.debug("Creating persistent disk for volume %s", volume.name)
        try:
            operation = self.disk_client.insert(
                project=self.config.project_id,
                zone=zone,
                disk_resource=disk,
            )
            gcp_resources.wait_for_extended_operation(operation, "persistent disk creation")
        except google.api_core.exceptions.Conflict:
            raise ComputeError(f"Volume {volume.name} already exists")
        created_disk = self.disk_client.get(
            project=self.config.project_id,
            zone=zone,
            disk=disk_name,
        )
        logger.debug("Created persistent disk for volume %s", volume.name)
        return VolumeProvisioningData(
            backend=BackendType.GCP,
            volume_id=created_disk.name,
            size_gb=created_disk.size_gb,
            availability_zone=zone,
            price=_get_volume_price(created_disk.size_gb),
            attachable=True,
            detachable=True,
            backend_data=GCPVolumeDiskBackendData(
                disk_type=gcp_resources.full_resource_name_to_name(disk.type_),
            ).json(),
        )

    def delete_volume(self, volume: Volume):
        logger.debug("Deleting persistent disk for volume %s", volume.name)
        try:
            operation = self.disk_client.delete(
                project=self.config.project_id,
                zone=get_or_error(volume.provisioning_data).availability_zone,
                disk=volume.volume_id,
            )
            gcp_resources.wait_for_extended_operation(operation, "persistent disk deletion")
        except google.api_core.exceptions.NotFound:
            logger.debug("Failed to find persistent disk for volume %s", volume.name)
            pass
        logger.debug("Deleted persistent disk for volume %s", volume.name)

    def attach_volume(
        self, volume: Volume, provisioning_data: JobProvisioningData
    ) -> VolumeAttachmentData:
        instance_id = provisioning_data.instance_id
        logger.debug(
            "Attaching persistent disk for volume %s to instance %s",
            volume.volume_id,
            instance_id,
        )
        if not gcp_resources.instance_type_supports_persistent_disk(
            provisioning_data.instance_type.name
        ):
            raise ComputeError(
                f"Instance type {provisioning_data.instance_type.name} does not support Persistent disk volumes"
            )

        zone = get_or_error(volume.provisioning_data).availability_zone
        is_tpu = _is_tpu_provisioning_data(provisioning_data)
        try:
            disk = self.disk_client.get(
                project=self.config.project_id,
                zone=zone,
                disk=volume.volume_id,
            )
            disk_url = disk.self_link
        except google.api_core.exceptions.NotFound:
            raise ComputeError("Persistent disk found")

        try:
            if is_tpu:
                get_node_request = tpu_v2.GetNodeRequest(
                    name=f"projects/{self.config.project_id}/locations/{zone}/nodes/{instance_id}",
                )
                tpu_node = self.tpu_client.get_node(get_node_request)

                # Python API to attach a disk to a TPU is not documented,
                # so we follow the code from the gcloud CLI:
                # https://github.com/twistedpair/google-cloud-sdk/blob/26ab5a281d56b384cc25750f3279a27afe5b499f/google-cloud-sdk/lib/googlecloudsdk/command_lib/compute/tpus/tpu_vm/util.py#L113
                source_disk = (
                    f"projects/{self.config.project_id}/zones/{zone}/disks/{volume.volume_id}"
                )
                # create_instance() has already attached the disks
                # if the TPU is provisioned on the run submission via run_job()
                for i, disk in enumerate(tpu_node.data_disks, start=1):
                    if disk.source_disk == source_disk:
                        device_name = f"persistent-disk-{i}"
                        logger.debug(
                            "Persistent disk for volume %s is already attached to instance %s",
                            volume.volume_id,
                            instance_id,
                        )
                        return VolumeAttachmentData(device_name=device_name)
                attached_disk = tpu_v2.AttachedDisk(
                    source_disk=source_disk,
                    mode=tpu_v2.AttachedDisk.DiskMode.READ_WRITE,
                )
                tpu_node.data_disks.append(attached_disk)
                # Cannot set device name for TPUs, so use default naming
                device_name = f"persistent-disk-{len(tpu_node.data_disks)}"
                update_node_request = tpu_v2.UpdateNodeRequest(
                    node=tpu_node,
                    update_mask="dataDisks",
                )
                operation = self.tpu_client.update_node(update_node_request)
                gcp_resources.wait_for_operation(operation, "persistent disk attachment")
            else:
                attached_disk = compute_v1.AttachedDisk()
                attached_disk.source = disk_url
                attached_disk.auto_delete = False
                attached_disk.device_name = f"pd-{volume.volume_id}"
                device_name = attached_disk.device_name
                operation = self.instances_client.attach_disk(
                    project=self.config.project_id,
                    zone=zone,
                    instance=instance_id,
                    attached_disk_resource=attached_disk,
                )
                gcp_resources.wait_for_extended_operation(operation, "persistent disk attachment")
        except google.api_core.exceptions.NotFound:
            raise ComputeError("Disk or instance not found")
        logger.debug(
            "Attached persistent disk for volume %s to instance %s", volume.volume_id, instance_id
        )
        return VolumeAttachmentData(device_name=device_name)

    def detach_volume(
        self, volume: Volume, provisioning_data: JobProvisioningData, force: bool = False
    ):
        instance_id = provisioning_data.instance_id
        logger.debug(
            "Detaching persistent disk for volume %s from instance %s",
            volume.volume_id,
            instance_id,
        )
        zone = get_or_error(volume.provisioning_data).availability_zone
        attachment_data = get_or_error(volume.get_attachment_data_for_instance(instance_id))
        is_tpu = _is_tpu_provisioning_data(provisioning_data)
        if is_tpu:
            try:
                get_node_request = tpu_v2.GetNodeRequest(
                    name=f"projects/{self.config.project_id}/locations/{zone}/nodes/{instance_id}",
                )
                tpu_node = self.tpu_client.get_node(get_node_request)
            except google.api_core.exceptions.NotFound:
                raise ComputeError("Instance not found")

            source_disk = (
                f"projects/{self.config.project_id}/zones/{zone}/disks/{volume.volume_id}"
            )
            tpu_node.data_disks = [
                disk for disk in tpu_node.data_disks if disk.source_disk != source_disk
            ]
            update_node_request = tpu_v2.UpdateNodeRequest(
                node=tpu_node,
                update_mask="dataDisks",
            )
            operation = self.tpu_client.update_node(update_node_request)
            gcp_resources.wait_for_operation(operation, "persistent disk detachment")
        else:
            operation = self.instances_client.detach_disk(
                project=self.config.project_id,
                zone=get_or_error(volume.provisioning_data).availability_zone,
                instance=instance_id,
                device_name=attachment_data.device_name,
            )
            gcp_resources.wait_for_extended_operation(operation, "persistent disk detachment")
        logger.debug(
            "Detached persistent disk for volume %s from instance %s",
            volume.volume_id,
            instance_id,
        )

    @cachedmethod(
        cache=lambda self: self._extra_subnets_cache,
        lock=lambda self: self._extra_subnets_cache_lock,
    )
    def _get_extra_subnets(
        self,
        region: str,
        instance_type_name: str,
    ) -> List[Tuple[str, str]]:
        if self.config.extra_vpcs is None:
            return []
        if instance_type_name == "a3-megagpu-8g":
            subnets_num = 8
        elif instance_type_name in ["a3-edgegpu-8g", "a3-highgpu-8g"]:
            subnets_num = 4
        else:
            return []
        extra_subnets = []
        for vpc_name in self.config.extra_vpcs[:subnets_num]:
            subnet = gcp_resources.get_vpc_subnet_or_error(
                subnetworks_client=self.subnetworks_client,
                vpc_project_id=self.config.vpc_project_id or self.config.project_id,
                vpc_name=vpc_name,
                region=region,
            )
            vpc_resource_name = gcp_resources.vpc_name_to_vpc_resource_name(
                project_id=self.config.vpc_project_id or self.config.project_id,
                vpc_name=vpc_name,
            )
            extra_subnets.append((vpc_resource_name, subnet))
        return extra_subnets


def _supported_instances_and_zones(
    regions: List[str],
) -> Optional[Callable[[InstanceOffer], bool]]:
    def _filter(offer: InstanceOffer) -> bool:
        # strip zone
        if offer.region[:-2] not in regions:
            return False
        # remove multi-host TPUs for initial release
        if _is_tpu(offer.instance.name) and not _is_single_host_tpu(offer.instance.name):
            return False
        for family in [
            "m4-",
            "c4-",
            "n4-",
            "h3-",
            "n2-",
            "e2-medium",
            "e2-standard-",
            "e2-highmem-",
            "e2-highcpu-",
            "m1-",
            "a2-",
            "a3-",
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
    if gpu.name == "H100":
        # H100 and H100_MEGA quotas are not returned by `regions_client.list`
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


def _get_image_id(instance_type_name: str, cuda: bool) -> str:
    if instance_type_name == "a3-megagpu-8g":
        image_name = "dstack-a3mega-5"
    elif instance_type_name in ["a3-edgegpu-8g", "a3-highgpu-8g"]:
        return "projects/cos-cloud/global/images/cos-105-17412-535-78"
    elif cuda:
        image_name = f"dstack-cuda-{version.base_image}"
    else:
        image_name = f"dstack-{version.base_image}"
    image_name = image_name.replace(".", "-")
    return f"projects/dstack/global/images/{image_name}"


def _get_gateway_image_id() -> str:
    return "projects/ubuntu-os-cloud/global/images/ubuntu-2204-jammy-v20230714"


def _get_user_data(authorized_keys: List[str], instance_type_name: str) -> str:
    base_path = None
    bin_path = None
    backend_shim_env = None
    if instance_type_name in ["a3-edgegpu-8g", "a3-highgpu-8g"]:
        # In the COS image the / file system is not writable.
        # /home and /var are writable but not executable.
        # Only /etc is both writable and executable, so use it for shim/runner binaries.
        # See: https://cloud.google.com/container-optimized-os/docs/concepts/disks-and-filesystem
        base_path = bin_path = "/etc"
        backend_shim_env = {
            # In COS nvidia binaries are not installed on PATH by default.
            # Set so that shim can run nvidia-smi.
            "PATH": "/var/lib/nvidia/bin:$PATH",
        }
    return get_user_data(
        authorized_keys=authorized_keys,
        backend_specific_commands=_get_backend_specific_commands(
            instance_type_name=instance_type_name,
        ),
        base_path=base_path,
        bin_path=bin_path,
        backend_shim_env=backend_shim_env,
    )


def _get_backend_specific_commands(instance_type_name: str) -> List[str]:
    if instance_type_name == "a3-megagpu-8g":
        return tcpx_features.get_backend_specific_commands_tcpxo()
    if instance_type_name in ["a3-edgegpu-8g", "a3-highgpu-8g"]:
        return tcpx_features.get_backend_specific_commands_tcpx()
    return []


def _get_volume_price(size: int) -> float:
    # https://cloud.google.com/compute/disks-image-pricing#persistentdisk
    # The price is different in different regions. Take max across supported regions.
    return size * 0.12


def _get_tpu_startup_script(authorized_keys: List[str]) -> str:
    commands = get_shim_commands(
        authorized_keys=authorized_keys, is_privileged=True, pjrt_device="TPU"
    )
    startup_script = " ".join([" && ".join(commands)])
    startup_script = "#! /bin/bash\n" + startup_script
    return startup_script


def _is_tpu(instance_name: str) -> bool:
    parts = instance_name.split("-")
    if len(parts) == 2:
        version, cores = parts
        if version in TPU_VERSIONS and cores.isdigit():
            return True
    return False


def _get_tpu_runtime_version(instance_name: str) -> str:
    tpu_version = _get_tpu_version(instance_name)
    if tpu_version == "v6e":
        return "v2-alpha-tpuv6e"
    elif tpu_version == "v5litepod":
        return "v2-alpha-tpuv5-lite"
    return "tpu-ubuntu2204-base"


def _get_tpu_version(instance_name: str) -> str:
    return instance_name.split("-")[0]


def _is_single_host_tpu(instance_name: str) -> bool:
    parts = instance_name.split("-")
    if len(parts) != 2:
        logger.info("Skipping unknown TPU: %s", instance_name)
        return False
    tpu_version, tensor_cores = parts
    try:
        tensor_cores = int(tensor_cores)
    except ValueError:
        logger.info("Skipping TPU due to invalid number of tensor cores: %s", tensor_cores)
        return False
    if tpu_version in ["v2", "v3", "v5p", "v5litepod", "v6e"]:
        return tensor_cores <= 8
    elif tpu_version == "v4":
        return False
    else:
        logger.info("Skipping unknown TPU: %s", instance_name)
        return False


def _get_tpu_data_disks(
    project_id: str, volumes: Optional[List[Volume]]
) -> List[tpu_v2.AttachedDisk]:
    if volumes is None:
        return []
    return [_get_tpu_data_disk_for_volume(project_id, volume) for volume in volumes]


def _get_tpu_data_disk_for_volume(project_id: str, volume: Volume) -> tpu_v2.AttachedDisk:
    zone = get_or_error(volume.provisioning_data).availability_zone
    source_disk = f"projects/{project_id}/zones/{zone}/disks/{volume.volume_id}"
    attached_disk = tpu_v2.AttachedDisk(
        source_disk=source_disk,
        mode=tpu_v2.AttachedDisk.DiskMode.READ_WRITE,
    )
    return attached_disk


def _is_tpu_provisioning_data(provisioning_data: JobProvisioningData) -> bool:
    is_tpu = False
    if provisioning_data.backend_data:
        backend_data_dict = json.loads(provisioning_data.backend_data)
        is_tpu = backend_data_dict.get("is_tpu", False)
    return is_tpu


def _get_instance_ip(instance: Instance, public_ip: bool) -> str:
    if public_ip:
        return instance.network_interfaces[0].access_configs[0].nat_i_p
    return instance.network_interfaces[0].network_i_p
