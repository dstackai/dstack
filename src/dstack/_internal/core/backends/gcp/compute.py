import concurrent.futures
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Callable, Dict, List, Literal, Optional, Tuple

import google.api_core.exceptions
import google.cloud.compute_v1 as compute_v1
import gpuhunt
from cachetools import TTLCache, cachedmethod
from google.cloud import tpu_v2
from google.cloud.compute_v1.types.compute import Instance
from gpuhunt import KNOWN_TPUS
from pydantic import ValidationError

import dstack._internal.core.backends.gcp.auth as auth
import dstack._internal.core.backends.gcp.resources as gcp_resources
from dstack._internal import settings
from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeTTLCache,
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithGatewayLoadBalancerSupport,
    ComputeWithGatewaySupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithPrivateGatewaySupport,
    ComputeWithPrivilegedSupport,
    ComputeWithReservationSupport,
    ComputeWithVolumeSupport,
    generate_unique_gateway_instance_name,
    generate_unique_instance_name,
    generate_unique_short_backend_name,
    generate_unique_volume_name,
    get_gateway_user_data,
    get_shim_commands,
    get_user_data,
    merge_tags,
    requires_nvidia_proprietary_kernel_modules,
)
from dstack._internal.core.backends.base.offers import (
    OfferModifier,
    get_catalog_offers,
    get_offers_disk_modifier,
)
from dstack._internal.core.backends.gcp.features import tcpx as tcpx_features
from dstack._internal.core.backends.gcp.models import GCPConfig
from dstack._internal.core.consts import DSTACK_OS_IMAGE_WITH_PROPRIETARY_NVIDIA_KERNEL_MODULES
from dstack._internal.core.errors import (
    ComputeError,
    ComputeResourceNotFoundError,
    NoCapacityError,
    PlacementGroupInUseError,
    ProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import (
    CoreModel,
    validate_extra_ignore,
    validate_json_extra_ignore,
)
from dstack._internal.core.models.gateways import (
    GatewayLoadBalancerConfiguration,
    GatewayLoadBalancerData,
    GatewayReplicaConfiguration,
    GatewayReplicaProvisioningData,
)
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
    Resources,
)
from dstack._internal.core.models.placement import PlacementGroup, PlacementGroupProvisioningData
from dstack._internal.core.models.resources import Memory, Range
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.core.models.volumes import (
    GCPVolumeConfiguration,
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
# Pattern from https://cloud.google.com/compute/docs/instances/reservations-consume#consuming_instances_from_a_specific_reservation
RESERVATION_PATTERN = re.compile(
    r"projects/(?P<project_id>[a-z0-9-]+)/reservations/(?P<reservation_name>[a-z0-9-]+)"
)
RESOURCE_NAME_PATTERN = re.compile(r"[a-z0-9-]+")
TPU_VERSIONS = [tpu.name for tpu in KNOWN_TPUS]
DEFAULT_GATEWAY_INSTANCE_TYPE = "e2-medium"


class GCPOfferBackendData(CoreModel):
    is_dws_calendar_mode: bool = False


class GCPVolumeDiskBackendData(CoreModel):
    type: Literal["disk"] = "disk"
    disk_type: str


class GCPGatewayBackendData(CoreModel):
    zone: str
    instance_group_name: str
    health_check_name: str
    backend_service_name: str
    url_map_name: str
    target_http_proxy_name: str
    forwarding_rule_name: str


class GCPCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithMultinodeSupport,
    ComputeWithReservationSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithGatewaySupport,
    ComputeWithPrivateGatewaySupport,
    ComputeWithGatewayLoadBalancerSupport,
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
        self.reservations_client = compute_v1.ReservationsClient(credentials=self.credentials)
        self.instance_groups_client = compute_v1.InstanceGroupsClient(credentials=self.credentials)
        self.region_health_checks_client = compute_v1.RegionHealthChecksClient(
            credentials=self.credentials
        )
        self.region_backend_services_client = compute_v1.RegionBackendServicesClient(
            credentials=self.credentials
        )
        self.region_url_maps_client = compute_v1.RegionUrlMapsClient(credentials=self.credentials)
        self.region_target_http_proxies_client = compute_v1.RegionTargetHttpProxiesClient(
            credentials=self.credentials
        )
        self.forwarding_rules_client = compute_v1.ForwardingRulesClient(
            credentials=self.credentials
        )
        self._usable_subnets_cache = ComputeTTLCache(cache=TTLCache(maxsize=1, ttl=120))
        # Smaller TTL since we check the reservation's in_use_count, which can change often
        self._reservation_cache = ComputeTTLCache(cache=TTLCache(maxsize=8, ttl=20))

    def get_all_offers_with_availability(
        self, unallocated_resources: bool
    ) -> List[InstanceOfferWithAvailability]:
        regions = get_or_error(self.config.regions)
        zones_by_key: Dict[Tuple, List[str]] = {}
        catalog_item_filter = _make_catalog_item_filter(regions, zones_by_key)
        offers = get_catalog_offers(
            backend=BackendType.GCP,
            catalog_item_filter=catalog_item_filter,
        )
        quotas: Dict[str, Dict[str, float]] = defaultdict(dict)
        for region in self.regions_client.list(project=self.config.project_id):
            for quota in region.quotas:
                quotas[region.name][quota.metric] = quota.limit - quota.usage

        offers_with_availability = []
        for offer in offers:
            region = offer.region[:-2]  # strip zone
            gpu_name = (
                offer.instance.resources.gpus[0].name if offer.instance.resources.gpus else None
            )
            key = _offer_dedup_key(
                offer.instance.name, offer.instance.resources.spot, gpu_name, region
            )
            availability = InstanceAvailability.NO_QUOTA
            if _has_gpu_quota(quotas[region], offer.instance.resources):
                availability = InstanceAvailability.UNKNOWN
            # todo quotas: cpu, memory, global gpu, tpu
            offer_with_availability = offer.with_availability(
                availability=availability,
                availability_zones=zones_by_key.get(key, []),
            )
            offers_with_availability.append(offer_with_availability)
            offer_with_availability.region = region
        return offers_with_availability

    def get_offers_modifiers(
        self, requirements: Requirements, full_offers: bool
    ) -> Iterable[OfferModifier]:
        modifiers = []

        if requirements.reservation:
            zone_to_reservation = self._find_reservation(requirements.reservation)

            def reservation_modifier(
                offer: InstanceOfferWithAvailability,
            ) -> Optional[InstanceOfferWithAvailability]:
                if offer.instance.resources.spot:
                    return None
                assert offer.availability_zones is not None
                matching_zones = []
                zones_with_capacity = []
                for zone in offer.availability_zones:
                    reservation = zone_to_reservation.get(zone)
                    if reservation is not None and _offer_matches_reservation(offer, reservation):
                        matching_zones.append(zone)
                        if _reservation_has_capacity(reservation):
                            zones_with_capacity.append(zone)
                if not matching_zones:
                    return None
                offer = offer.model_copy(deep=True)
                if zones_with_capacity:
                    offer.availability_zones = zones_with_capacity
                else:
                    offer.availability_zones = matching_zones
                    offer.availability = InstanceAvailability.NOT_AVAILABLE
                return offer

            modifiers.append(reservation_modifier)

        modifiers.append(get_offers_disk_modifier(CONFIGURABLE_DISK_SIZE, requirements))
        return modifiers

    def get_offers_post_filter(
        self, requirements: Requirements
    ) -> Optional[Callable[[InstanceOfferWithAvailability], bool]]:
        if requirements.reservation is None:

            def reserved_offers_filter(offer: InstanceOfferWithAvailability) -> bool:
                """Remove reserved-only offers"""
                if validate_extra_ignore(
                    GCPOfferBackendData, offer.backend_data
                ).is_dws_calendar_mode:
                    return False
                return True

            return reserved_offers_filter

        return None

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
        # Use the subnet configured in `subnetworks` for the region if any,
        # otherwise choose any usable subnet in the VPC.
        subnetwork = self._get_vpc_subnet(instance_offer.region)
        extra_subnets = self._get_extra_subnets(
            region=instance_offer.region,
            instance_type_name=instance_offer.instance.name,
        )
        roce_subnets = self._get_roce_subnets(
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
            startup_script = _get_tpu_startup_script()
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

        image = _get_image(
            instance_type_name=instance_offer.instance.name,
            gpu_name=(
                instance_offer.instance.resources.gpus[0].name
                if len(instance_offer.instance.resources.gpus) > 0
                else None
            ),
        )

        for zone in zones:
            reservation = None
            if instance_config.reservation:
                reservation = self._find_reservation(instance_config.reservation).get(zone)
                if reservation is None:
                    logger.warning(
                        "Reservation %s no longer exists in zone %s",
                        instance_config.reservation,
                        zone,
                    )
                    continue
            request = compute_v1.InsertInstanceRequest()
            request.zone = zone
            request.project = self.config.project_id
            request.instance_resource = gcp_resources.create_instance_struct(
                disk_size=disk_size,
                image_id=image.id,
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
                    is_ufw_installed=image.is_ufw_installed,
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
                roce_subnetworks=roce_subnets,
                allocate_public_ip=allocate_public_ip,
                placement_policy=placement_policy,
                reservation=reservation,
            )
            try:
                # GCP needs some time to return an error in case of no capacity (< 30s).
                # Call wait_for_operation() to get the capacity error and try another option.
                # If the request succeeds, we'll probably timeout and update_provisioning_data() will get hostname.
                operation = self.instances_client.insert(request=request)
                gcp_resources.wait_for_extended_operation(operation, timeout=30)
            except google.api_core.exceptions.BadRequest as e:
                if "Network profile only allows resource creation in location" in e.message:
                    # A hack to find the correct RoCE VPC zone by trial and error.
                    # Could be better to find it via the API.
                    logger.debug("Got GCP error when provisioning a VM: %s", e)
                    continue
                raise
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

    def are_placement_groups_compatible_with_reservations(self, backend_type: BackendType) -> bool:
        # Cannot use our own placement policies when provisioning in a reservation.
        # Instead, we use the placement policy defined in reservation settings.
        return False

    def create_gateway_replica(
        self,
        configuration: GatewayReplicaConfiguration,
        gateway_backend_data: Optional[str] = None,
    ) -> GatewayReplicaProvisioningData:
        if self.config.vpc_project_id is None:
            gcp_resources.create_gateway_firewall_rules(
                firewalls_client=self.firewalls_client,
                project_id=self.config.project_id,
                network=self.config.vpc_resource_name,
            )
        if gateway_backend_data is not None:
            zone = validate_json_extra_ignore(GCPGatewayBackendData, gateway_backend_data).zone
        else:
            zone = self._get_gateway_zone(configuration.region)

        instance_name = generate_unique_gateway_instance_name(
            configuration, max_length=gcp_resources.MAX_RESOURCE_NAME_LEN
        )
        # Use the subnet configured in `subnetworks` for the region if any,
        # otherwise choose any usable subnet in the VPC.
        subnetwork = self._get_vpc_subnet(configuration.region)

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
            machine_type=configuration.instance_type or DEFAULT_GATEWAY_INSTANCE_TYPE,
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
        try:
            operation = self.instances_client.insert(request=request)
            gcp_resources.wait_for_extended_operation(operation, "instance creation")
        except (
            google.api_core.exceptions.ServiceUnavailable,
            google.api_core.exceptions.ClientError,
        ) as e:
            raise ComputeError(f"GCP error: {e.message}")
        instance = self.instances_client.get(
            project=self.config.project_id, zone=zone, instance=instance_name
        )
        return GatewayReplicaProvisioningData(
            instance_id=instance_name,
            region=configuration.region,  # used for instance termination
            availability_zone=zone,
            ip_address=_get_instance_ip(instance, configuration.public_ip),
            backend_data=json.dumps({"zone": zone}),
        )

    def terminate_gateway_replica(
        self,
        instance_id: str,
        configuration: GatewayReplicaConfiguration,
        backend_data: Optional[str] = None,
    ):
        self.terminate_instance(
            instance_id=instance_id,
            region=configuration.region,
            backend_data=backend_data,
        )

    def _get_gateway_zone(self, region: str) -> str:
        for i in self.regions_client.list(project=self.config.project_id):
            if i.name == region:
                return i.zones[0].split("/")[-1]
        raise ComputeResourceNotFoundError()

    def create_gateway_load_balancer(
        self,
        configuration: GatewayLoadBalancerConfiguration,
    ) -> GatewayLoadBalancerData:
        assert configuration.certificate is None

        zone = self._get_gateway_zone(configuration.region)

        proxy_subnet_cidr = gcp_resources.get_proxy_only_subnet_cidr_or_error(
            subnetworks_client=self.subnetworks_client,
            project_id=self.config.vpc_project_id or self.config.project_id,
            region=configuration.region,
            network=self.config.vpc_resource_name,
        )
        subnetwork = None
        if not configuration.public_ip:
            subnetwork = gcp_resources.get_vpc_subnet_or_error(
                vpc_name=self.config.vpc_name or "default",
                region=configuration.region,
                usable_subnets=self._list_usable_subnets(),
                subnetwork_name=(
                    self.config.subnetworks.get(configuration.region)
                    if self.config.subnetworks
                    else None
                ),
            )
        if self.config.vpc_project_id is None:
            gcp_resources.create_gateway_lb_healthcheck_firewall_rule(
                firewalls_client=self.firewalls_client,
                project_id=self.config.project_id,
                network=self.config.vpc_resource_name,
            )
            gcp_resources.create_gateway_lb_proxy_firewall_rule(
                firewalls_client=self.firewalls_client,
                project_id=self.config.project_id,
                region=configuration.region,
                proxy_subnet_cidr=proxy_subnet_cidr,
                network=self.config.vpc_resource_name,
            )

        name = generate_unique_short_backend_name()
        instance_group_name = f"{name}-ig"
        health_check_name = f"{name}-hc"
        backend_service_name = f"{name}-bs"
        url_map_name = f"{name}-um"
        target_http_proxy_name = f"{name}-proxy"
        forwarding_rule_name = f"{name}-fr"

        instance_group_resource_name = (
            f"projects/{self.config.project_id}/zones/{zone}/instanceGroups/{instance_group_name}"
        )
        health_check_resource_name = (
            f"projects/{self.config.project_id}/regions/{configuration.region}"
            f"/healthChecks/{health_check_name}"
        )
        backend_service_resource_name = (
            f"projects/{self.config.project_id}/regions/{configuration.region}"
            f"/backendServices/{backend_service_name}"
        )
        url_map_resource_name = (
            f"projects/{self.config.project_id}/regions/{configuration.region}"
            f"/urlMaps/{url_map_name}"
        )
        target_http_proxy_resource_name = (
            f"projects/{self.config.project_id}/regions/{configuration.region}"
            f"/targetHttpProxies/{target_http_proxy_name}"
        )

        logger.debug("Creating instance group for gateway %s...", configuration.gateway_name)
        instance_group = compute_v1.InstanceGroup()
        instance_group.name = instance_group_name
        instance_group.named_ports = [compute_v1.NamedPort(name="http", port=80)]
        operation = self.instance_groups_client.insert(
            project=self.config.project_id, zone=zone, instance_group_resource=instance_group
        )
        gcp_resources.wait_for_extended_operation(operation, "instance group creation")
        logger.debug("Created instance group for gateway %s.", configuration.gateway_name)

        logger.debug("Creating health check for gateway %s...", configuration.gateway_name)
        health_check = compute_v1.HealthCheck()
        health_check.name = health_check_name
        health_check.type_ = compute_v1.HealthCheck.Type.HTTP.name
        health_check.http_health_check = compute_v1.HTTPHealthCheck(port=80)
        operation = self.region_health_checks_client.insert(
            project=self.config.project_id,
            region=configuration.region,
            health_check_resource=health_check,
        )
        gcp_resources.wait_for_extended_operation(operation, "health check creation")
        logger.debug("Created health check for gateway %s.", configuration.gateway_name)

        logger.debug("Creating backend service for gateway %s...", configuration.gateway_name)
        load_balancing_scheme = (
            compute_v1.BackendService.LoadBalancingScheme.EXTERNAL_MANAGED.name
            if configuration.public_ip
            else compute_v1.BackendService.LoadBalancingScheme.INTERNAL_MANAGED.name
        )
        backend_service = compute_v1.BackendService()
        backend_service.name = backend_service_name
        backend_service.load_balancing_scheme = load_balancing_scheme
        backend_service.protocol = compute_v1.BackendService.Protocol.HTTP.name
        backend_service.port_name = "http"
        backend_service.health_checks = [health_check_resource_name]
        backend_service.backends = [
            compute_v1.Backend(
                group=instance_group_resource_name,
                balancing_mode=compute_v1.Backend.BalancingMode.UTILIZATION.name,
                capacity_scaler=1.0,
            )
        ]
        operation = self.region_backend_services_client.insert(
            project=self.config.project_id,
            region=configuration.region,
            backend_service_resource=backend_service,
        )
        gcp_resources.wait_for_extended_operation(operation, "backend service creation")
        logger.debug("Created backend service for gateway %s.", configuration.gateway_name)

        logger.debug("Creating URL map for gateway %s...", configuration.gateway_name)
        url_map = compute_v1.UrlMap()
        url_map.name = url_map_name
        url_map.default_service = backend_service_resource_name
        operation = self.region_url_maps_client.insert(
            project=self.config.project_id,
            region=configuration.region,
            url_map_resource=url_map,
        )
        gcp_resources.wait_for_extended_operation(operation, "URL map creation")
        logger.debug("Created URL map for gateway %s.", configuration.gateway_name)

        logger.debug("Creating target HTTP proxy for gateway %s...", configuration.gateway_name)
        target_http_proxy = compute_v1.TargetHttpProxy()
        target_http_proxy.name = target_http_proxy_name
        target_http_proxy.url_map = url_map_resource_name
        operation = self.region_target_http_proxies_client.insert(
            project=self.config.project_id,
            region=configuration.region,
            target_http_proxy_resource=target_http_proxy,
        )
        gcp_resources.wait_for_extended_operation(operation, "target HTTP proxy creation")
        logger.debug("Created target HTTP proxy for gateway %s.", configuration.gateway_name)

        logger.debug("Creating forwarding rule for gateway %s...", configuration.gateway_name)
        forwarding_rule = compute_v1.ForwardingRule()
        forwarding_rule.name = forwarding_rule_name
        forwarding_rule.load_balancing_scheme = load_balancing_scheme
        forwarding_rule.I_p_protocol = compute_v1.ForwardingRule.IPProtocolEnum.TCP.name
        forwarding_rule.port_range = "80"
        forwarding_rule.target = target_http_proxy_resource_name
        forwarding_rule.network = self.config.vpc_resource_name
        if subnetwork is not None:
            forwarding_rule.subnetwork = subnetwork
        operation = self.forwarding_rules_client.insert(
            project=self.config.project_id,
            region=configuration.region,
            forwarding_rule_resource=forwarding_rule,
        )
        gcp_resources.wait_for_extended_operation(operation, "forwarding rule creation")
        forwarding_rule = self.forwarding_rules_client.get(
            project=self.config.project_id,
            region=configuration.region,
            forwarding_rule=forwarding_rule_name,
        )
        logger.debug("Created forwarding rule for gateway %s.", configuration.gateway_name)

        return GatewayLoadBalancerData(
            hostname=forwarding_rule.I_p_address,
            backend_data=GCPGatewayBackendData(
                zone=zone,
                instance_group_name=instance_group_name,
                health_check_name=health_check_name,
                backend_service_name=backend_service_name,
                url_map_name=url_map_name,
                target_http_proxy_name=target_http_proxy_name,
                forwarding_rule_name=forwarding_rule_name,
            ).model_dump_json(),
        )

    def terminate_gateway_load_balancer(
        self,
        configuration: GatewayLoadBalancerConfiguration,
        backend_data: Optional[str],
    ) -> None:
        if backend_data is None:
            logger.error(
                "Failed to terminate load balancer for gateway %s: backend_data is None.",
                configuration.gateway_name,
            )
            return
        try:
            backend_data_parsed = validate_json_extra_ignore(GCPGatewayBackendData, backend_data)
        except ValidationError:
            logger.exception(
                "Failed to terminate load balancer for gateway %s: backend_data parsing error.",
                configuration.gateway_name,
            )
            return

        logger.debug(
            "Deleting load balancer resources for gateway %s...", configuration.gateway_name
        )
        for delete_call, verbose_name in [
            (
                lambda: self.forwarding_rules_client.delete(
                    project=self.config.project_id,
                    region=configuration.region,
                    forwarding_rule=backend_data_parsed.forwarding_rule_name,
                ),
                "forwarding rule deletion",
            ),
            (
                lambda: self.region_target_http_proxies_client.delete(
                    project=self.config.project_id,
                    region=configuration.region,
                    target_http_proxy=backend_data_parsed.target_http_proxy_name,
                ),
                "target HTTP proxy deletion",
            ),
            (
                lambda: self.region_url_maps_client.delete(
                    project=self.config.project_id,
                    region=configuration.region,
                    url_map=backend_data_parsed.url_map_name,
                ),
                "URL map deletion",
            ),
            (
                lambda: self.region_backend_services_client.delete(
                    project=self.config.project_id,
                    region=configuration.region,
                    backend_service=backend_data_parsed.backend_service_name,
                ),
                "backend service deletion",
            ),
            (
                lambda: self.region_health_checks_client.delete(
                    project=self.config.project_id,
                    region=configuration.region,
                    health_check=backend_data_parsed.health_check_name,
                ),
                "health check deletion",
            ),
            (
                lambda: self.instance_groups_client.delete(
                    project=self.config.project_id,
                    zone=backend_data_parsed.zone,
                    instance_group=backend_data_parsed.instance_group_name,
                ),
                "instance group deletion",
            ),
        ]:
            try:
                operation = delete_call()
                gcp_resources.wait_for_extended_operation(operation, verbose_name)
            except google.api_core.exceptions.NotFound:
                pass
        logger.debug("Deleted load balancer resources for gateway %s.", configuration.gateway_name)

    def register_gateway_replica_with_load_balancer(
        self,
        instance_id: str,
        configuration: GatewayLoadBalancerConfiguration,
        gateway_backend_data: Optional[str],
    ) -> None:
        if gateway_backend_data is None:
            raise ComputeError(
                f"Cannot register gateway {configuration.gateway_name} replica with load balancer:"
                " gateway_backend_data is None"
            )
        try:
            gateway_backend_data_parsed = validate_json_extra_ignore(
                GCPGatewayBackendData, gateway_backend_data
            )
        except ValidationError as e:
            raise ComputeError(
                f"Cannot register gateway {configuration.gateway_name} replica with load balancer:"
                " gateway_backend_data parsing error"
            ) from e

        instance_self_link = (
            "https://www.googleapis.com/compute/v1/projects/"
            f"{self.config.project_id}/zones/{gateway_backend_data_parsed.zone}/instances/{instance_id}"
        )
        logger.debug(
            "Registering gateway %s replica %s with instance group %s...",
            configuration.gateway_name,
            instance_id,
            gateway_backend_data_parsed.instance_group_name,
        )
        operation = self.instance_groups_client.add_instances(
            project=self.config.project_id,
            zone=gateway_backend_data_parsed.zone,
            instance_group=gateway_backend_data_parsed.instance_group_name,
            instance_groups_add_instances_request_resource=compute_v1.InstanceGroupsAddInstancesRequest(
                instances=[compute_v1.InstanceReference(instance=instance_self_link)]
            ),
        )
        gcp_resources.wait_for_extended_operation(operation, "instance group registration")
        logger.debug(
            "Registered gateway %s replica %s with instance group.",
            configuration.gateway_name,
            instance_id,
        )

    def deregister_gateway_replica_from_load_balancer(
        self,
        instance_id: str,
        configuration: GatewayLoadBalancerConfiguration,
        gateway_backend_data: Optional[str],
    ) -> None:
        if gateway_backend_data is None:
            raise ComputeError(
                f"Cannot deregister gateway {configuration.gateway_name} replica from load"
                " balancer: gateway_backend_data is None"
            )
        try:
            gateway_backend_data_parsed = validate_json_extra_ignore(
                GCPGatewayBackendData, gateway_backend_data
            )
        except ValidationError as e:
            raise ComputeError(
                f"Cannot deregister gateway {configuration.gateway_name} replica from load"
                " balancer: gateway_backend_data parsing error",
            ) from e

        instance_self_link = (
            "https://www.googleapis.com/compute/v1/projects/"
            f"{self.config.project_id}/zones/{gateway_backend_data_parsed.zone}/instances/{instance_id}"
        )
        logger.debug(
            "Deregistering gateway %s replica %s from instance group %s...",
            configuration.gateway_name,
            instance_id,
            gateway_backend_data_parsed.instance_group_name,
        )
        try:
            operation = self.instance_groups_client.remove_instances(
                project=self.config.project_id,
                zone=gateway_backend_data_parsed.zone,
                instance_group=gateway_backend_data_parsed.instance_group_name,
                instance_groups_remove_instances_request_resource=compute_v1.InstanceGroupsRemoveInstancesRequest(
                    instances=[compute_v1.InstanceReference(instance=instance_self_link)]
                ),
            )
            gcp_resources.wait_for_extended_operation(operation, "instance group deregistration")
        except google.api_core.exceptions.NotFound:
            pass
        except google.api_core.exceptions.BadRequest as e:
            # The instance was never added to the group or was already removed
            if "is not a member of" not in e.message:
                raise
        logger.debug(
            "Deregistered gateway %s replica %s from instance group.",
            configuration.gateway_name,
            instance_id,
        )

    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        assert isinstance(volume.configuration, GCPVolumeConfiguration)
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
                    ).model_dump_json(),
                )
        raise ComputeError(f"Persistent disk {volume.configuration.volume_id} not found")

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        assert isinstance(volume.configuration, GCPVolumeConfiguration)
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
            ).model_dump_json(),
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
        elif instance_type_name == "a4-highgpu-8g":
            subnets_num = 1  # 1 main + 1 extra + 8 RoCE
        else:
            return []
        extra_subnets = []
        for vpc_name in self.config.extra_vpcs[:subnets_num]:
            subnet = gcp_resources.get_vpc_subnet_or_error(
                vpc_name=vpc_name,
                region=region,
                usable_subnets=self._list_usable_subnets(),
            )
            vpc_resource_name = gcp_resources.vpc_name_to_vpc_resource_name(
                project_id=self.config.vpc_project_id or self.config.project_id,
                vpc_name=vpc_name,
            )
            extra_subnets.append((vpc_resource_name, subnet))
        return extra_subnets

    def _get_roce_subnets(
        self,
        region: str,
        instance_type_name: str,
    ) -> List[Tuple[str, str]]:
        if not self.config.roce_vpcs:
            return []
        if instance_type_name == "a4-highgpu-8g":
            nics_num = 8
        else:
            return []
        roce_vpc = self.config.roce_vpcs[0]  # roce_vpcs is validated to have at most 1 item
        subnets = gcp_resources.get_vpc_subnets(
            vpc_name=roce_vpc,
            region=region,
            usable_subnets=self._list_usable_subnets(),
        )
        if len(subnets) < nics_num:
            raise ComputeError(
                f"{instance_type_name} requires {nics_num} RoCE subnets,"
                f" but only {len(subnets)} are available in VPC {roce_vpc}"
            )
        vpc_resource_name = gcp_resources.vpc_name_to_vpc_resource_name(
            project_id=self.config.vpc_project_id or self.config.project_id,
            vpc_name=roce_vpc,
        )
        nic_subnets = []
        for subnet in subnets[:nics_num]:
            nic_subnets.append((vpc_resource_name, subnet))
        return nic_subnets

    @cachedmethod(
        cache=lambda self: self._usable_subnets_cache.cache,
        lock=lambda self: self._usable_subnets_cache.lock,
    )
    def _list_usable_subnets(self) -> list[compute_v1.UsableSubnetwork]:
        # To avoid hitting the `ListUsable requests per minute` system limit, we fetch all subnets
        # at once and cache them
        return gcp_resources.list_project_usable_subnets(
            subnetworks_client=self.subnetworks_client,
            project_id=self.config.vpc_project_id or self.config.project_id,
        )

    def _get_vpc_subnet(self, region: str) -> Optional[str]:
        if self.config.vpc_name is None:
            return None
        subnetworks = self.config.subnetworks
        return gcp_resources.get_vpc_subnet_or_error(
            vpc_name=self.config.vpc_name,
            region=region,
            usable_subnets=self._list_usable_subnets(),
            subnetwork_name=subnetworks.get(region) if subnetworks else None,
        )

    @cachedmethod(
        cache=lambda self: self._reservation_cache.cache,
        lock=lambda self: self._reservation_cache.lock,
    )
    def _find_reservation(self, configured_name: str) -> dict[str, compute_v1.Reservation]:
        if match := RESERVATION_PATTERN.fullmatch(configured_name):
            project_id = match.group("project_id")
            name = match.group("reservation_name")
        elif RESOURCE_NAME_PATTERN.fullmatch(configured_name):
            project_id = self.config.project_id
            name = configured_name
        else:
            # misconfigured or non-GCP
            return {}
        return gcp_resources.find_reservation(
            reservations_client=self.reservations_client,
            project_id=project_id,
            name=name,
        )


def _is_supported_gcp_instance(instance_name: str, gpu_name: Optional[str]) -> bool:
    """Check if the instance is supported by dstack."""
    if _is_tpu(instance_name) and not _is_single_host_tpu(instance_name):
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
        if instance_name.startswith(family):
            return True
    if gpu_name is not None and gpu_name not in {"K80", "P4", "P100"}:
        return True
    return False


def _offer_dedup_key(
    instance_name: str, spot: bool, gpu_name: Optional[str], region: str
) -> Tuple[str, bool, Optional[str], str]:
    """Key for deduplicating GCP per-zone items into per-region offers."""
    return (instance_name, spot, gpu_name, region)


def _make_catalog_item_filter(
    regions: List[str],
    zones_by_key: Dict[Tuple, List[str]],
) -> Callable[[gpuhunt.CatalogItem], bool]:
    """
    Returns a filter that checks region, instance support, and deduplicates
    per-zone items into per-region offers. Zones are collected in `zones_by_key`
    so the caller can attach them to offers later.
    """
    seen: set = set()

    def _filter(item: gpuhunt.CatalogItem) -> bool:
        region = item.location[:-2]
        if region not in regions:
            return False
        if not _is_supported_gcp_instance(item.instance_name, item.gpu_name):
            return False
        key = _offer_dedup_key(item.instance_name, item.spot, item.gpu_name, region)
        zones_by_key.setdefault(key, []).append(item.location)
        if key in seen:
            return False
        seen.add(key)
        return True

    return _filter


def _has_gpu_quota(quotas: Dict[str, float], resources: Resources) -> bool:
    if not resources.gpus:
        return True
    gpu = resources.gpus[0]
    if _is_tpu(gpu.name):
        return True
    if gpu.name in ["B200", "H100", "RTXPRO6000"]:
        # B200, H100, H100_MEGA, and RTXPRO6000 quotas are not returned by `regions_client.list`
        return True
    quota_name = f"NVIDIA_{gpu.name}_GPUS"
    if gpu.name == "A100" and gpu.memory_mib == 80 * 1024:
        quota_name = "NVIDIA_A100_80GB_GPUS"
    if resources.spot:
        quota_name = "PREEMPTIBLE_" + quota_name
    return len(resources.gpus) <= quotas.get(quota_name, 0)


def _offer_matches_reservation(
    offer: InstanceOfferWithAvailability, reservation: compute_v1.Reservation
) -> bool:
    if (
        reservation.specific_reservation is None
        or reservation.specific_reservation.instance_properties is None
    ):
        return False
    properties = reservation.specific_reservation.instance_properties
    if properties.machine_type != offer.instance.name:
        return False
    accelerators = properties.guest_accelerators or []
    if not accelerators and offer.instance.resources.gpus:
        return False
    if len(accelerators) > 1:
        logger.warning(
            "Expected 0 or 1 accelerator types per instance,"
            f" but {properties.machine_type} has {len(accelerators)}."
            f" Ignoring reservation {reservation.self_link}"
        )
        return False
    if accelerators:
        if accelerators[0].accelerator_count != len(offer.instance.resources.gpus):
            return False
        if (
            offer.instance.resources.gpus
            and gcp_resources.find_accelerator_name(
                offer.instance.resources.gpus[0].name,
                offer.instance.resources.gpus[0].memory_mib,
            )
            != accelerators[0].accelerator_type
        ):
            return False
    return True


def _reservation_has_capacity(reservation: compute_v1.Reservation) -> bool:
    return (
        reservation.specific_reservation is not None
        and reservation.specific_reservation.in_use_count is not None
        and reservation.specific_reservation.assured_count is not None
        and reservation.specific_reservation.in_use_count
        < reservation.specific_reservation.assured_count
    )


@dataclass
class GCPImage:
    id: str
    is_ufw_installed: bool


def _get_image(instance_type_name: str, gpu_name: Optional[str]) -> GCPImage:
    if instance_type_name == "a3-megagpu-8g":
        image_name = "dstack-a3mega-5"
        is_ufw_installed = False
    elif instance_type_name in ["a3-edgegpu-8g", "a3-highgpu-8g"]:
        return GCPImage(
            id="projects/cos-cloud/global/images/cos-105-17412-535-78",
            is_ufw_installed=False,
        )
    elif gpu_name is not None:
        if not requires_nvidia_proprietary_kernel_modules(gpu_name):
            image_name = (
                f"{settings.DSTACK_VM_BASE_IMAGE_PREFIX}"
                f"dstack-cuda-{settings.DSTACK_VM_BASE_IMAGE_VERSION}"
            )
        else:
            image_name = f"dstack-cuda-{DSTACK_OS_IMAGE_WITH_PROPRIETARY_NVIDIA_KERNEL_MODULES}"
        is_ufw_installed = True
    else:
        image_name = (
            f"{settings.DSTACK_VM_BASE_IMAGE_PREFIX}dstack-{settings.DSTACK_VM_BASE_IMAGE_VERSION}"
        )
        is_ufw_installed = True
    image_name = image_name.replace(".", "-")
    return GCPImage(
        id=f"projects/dstack/global/images/{image_name}",
        is_ufw_installed=is_ufw_installed,
    )


def _get_gateway_image_id() -> str:
    return "projects/ubuntu-os-cloud/global/images/ubuntu-2204-jammy-v20230714"


def _get_user_data(
    authorized_keys: List[str], instance_type_name: str, is_ufw_installed: bool
) -> str:
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
        # Instance-level firewall is optional on GCP. The main protection comes from GCP firewalls.
        # So only set up instance-level firewall as an additional measure if ufw is available.
        skip_firewall_setup=not is_ufw_installed,
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


def _get_tpu_startup_script() -> str:
    commands = get_shim_commands(is_privileged=True, pjrt_device="TPU")
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
