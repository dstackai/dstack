import re
from typing import Any, Dict, List, Optional

import botocore.client
import botocore.exceptions

import dstack.version as version
from dstack._internal.core.errors import BackendError, ComputeError, ComputeResourceNotFoundError
from dstack._internal.core.models.backends.aws import AWSOSImageConfig
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

DSTACK_ACCOUNT_ID = "142421590066"


def get_image_id_and_username(
    ec2_client: botocore.client.BaseClient,
    cuda: bool,
    image_config: Optional[AWSOSImageConfig] = None,
) -> tuple[str, str]:
    if image_config is not None:
        image = image_config.nvidia if cuda else image_config.cpu
        if image is None:
            logger.warning("%s image not configured", "nvidia" if cuda else "cpu")
            raise ComputeResourceNotFoundError()
        image_name = image.name
        image_owner = image.owner
        username = image.user
    else:
        image_name = (
            f"dstack-{version.base_image}" if not cuda else f"dstack-cuda-{version.base_image}"
        )
        image_owner = DSTACK_ACCOUNT_ID
        username = "ubuntu"
    response = ec2_client.describe_images(
        Filters=[{"Name": "name", "Values": [image_name]}], Owners=[image_owner]
    )
    images = sorted(
        (i for i in response["Images"] if i["State"] == "available"),
        key=lambda i: i["CreationDate"],
        reverse=True,
    )
    if not images:
        logger.warning("image '%s' not found", image_name)
        raise ComputeResourceNotFoundError()
    return images[0]["ImageId"], username


def create_security_group(
    ec2_client: botocore.client.BaseClient,
    project_id: str,
    vpc_id: Optional[str],
) -> str:
    security_group_name = "dstack_security_group_" + project_id.replace("-", "_").lower()
    describe_security_groups_filters = [
        {
            "Name": "group-name",
            "Values": [security_group_name],
        },
    ]
    if vpc_id is not None:
        describe_security_groups_filters.append(
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            }
        )
    response = ec2_client.describe_security_groups(Filters=describe_security_groups_filters)
    if response.get("SecurityGroups"):
        security_group = response["SecurityGroups"][0]
    else:
        create_security_group_kwargs = {}
        if vpc_id is not None:
            create_security_group_kwargs["VpcId"] = vpc_id
        security_group = ec2_client.create_security_group(
            Description="Generated by dstack",
            GroupName=security_group_name,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [
                        {"Key": "owner", "Value": "dstack"},
                        {"Key": "dstack_project", "Value": project_id},
                    ],
                },
            ],
            **create_security_group_kwargs,
        )
    security_group_id = security_group["GroupId"]

    _add_ingress_security_group_rule_if_missing(
        ec2_client=ec2_client,
        security_group=security_group,
        security_group_id=security_group_id,
        rule={
            "FromPort": 22,
            "ToPort": 22,
            "IpProtocol": "tcp",
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
        },
    )
    _add_ingress_security_group_rule_if_missing(
        ec2_client=ec2_client,
        security_group=security_group,
        security_group_id=security_group_id,
        rule={
            "IpProtocol": "-1",
            "UserIdGroupPairs": [{"GroupId": security_group_id}],
        },
    )
    _add_egress_security_group_rule_if_missing(
        ec2_client=ec2_client,
        security_group=security_group,
        security_group_id=security_group_id,
        rule={"IpProtocol": "-1"},
    )
    _add_egress_security_group_rule_if_missing(
        ec2_client=ec2_client,
        security_group=security_group,
        security_group_id=security_group_id,
        rule={
            "IpProtocol": "-1",
            "UserIdGroupPairs": [{"GroupId": security_group_id}],
        },
    )
    return security_group_id


def create_instances_struct(
    disk_size: int,
    image_id: str,
    instance_type: str,
    iam_instance_profile_arn: Optional[str],
    user_data: str,
    tags: List[Dict[str, str]],
    security_group_id: str,
    spot: bool,
    subnet_id: Optional[str] = None,
    allocate_public_ip: bool = True,
    placement_group_name: Optional[str] = None,
    enable_efa: bool = False,
    max_efa_interfaces: int = 0,
    reservation_id: Optional[str] = None,
    is_capacity_block: bool = False,
) -> Dict[str, Any]:
    struct: Dict[str, Any] = dict(
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": disk_size,
                    "VolumeType": "gp2",
                },
            }
        ],
        ImageId=image_id,
        InstanceType=instance_type,
        MinCount=1,
        MaxCount=1,
        UserData=user_data,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": tags,
            },
        ],
    )
    if iam_instance_profile_arn:
        struct["IamInstanceProfile"] = {"Arn": iam_instance_profile_arn}
    if spot:
        struct["InstanceMarketOptions"] = {
            "MarketType": "spot",
            "SpotOptions": {
                "SpotInstanceType": "one-time",
                "InstanceInterruptionBehavior": "terminate",
            },
        }

    if is_capacity_block:
        struct["InstanceMarketOptions"] = {"MarketType": "capacity-block"}
    if enable_efa and not subnet_id:
        raise ComputeError("EFA requires subnet")
    # AWS allows specifying either NetworkInterfaces for specific subnet_id
    # or instance-level SecurityGroupIds in case of no specific subnet_id, not both.
    if subnet_id is not None:
        # If the instance type supports multiple cards, we request multiple interfaces only if not allocate_public_ip
        # due to the limitation: "AssociatePublicIpAddress [...] You cannot specify more than one
        # network interface in the request".
        # Error message: "(InvalidParameterCombination) when calling the RunInstances operation:
        # The associatePublicIPAddress parameter cannot be specified when launching with
        # multiple network interfaces".
        # See: https://stackoverflow.com/questions/49882121
        # If we need more than one card, we should either use Elastic IP (AWS-recommended way) or
        # create the instance with one interface and add the rest later (the latter is not tested
        # and may or may not work).
        struct["NetworkInterfaces"] = [
            {
                "AssociatePublicIpAddress": allocate_public_ip,
                "DeviceIndex": 0,
                "SubnetId": subnet_id,
                "Groups": [security_group_id],
                "InterfaceType": "efa" if max_efa_interfaces > 0 else "interface",
            },
        ]

        if max_efa_interfaces > 1 and allocate_public_ip is False:
            for i in range(1, max_efa_interfaces):
                # Set to efa-only to use interfaces exclusively for GPU-to-GPU communication
                interface_type = "efa-only"
                if instance_type == "p5.48xlarge":
                    # EFA configuration for P5 instances:
                    # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa-acc-inst-types.html#efa-for-p5
                    interface_type = "efa" if i % 4 == 0 else "efa-only"
                struct["NetworkInterfaces"].append(
                    {
                        "AssociatePublicIpAddress": allocate_public_ip,
                        "NetworkCardIndex": i,
                        "DeviceIndex": 1,
                        "SubnetId": subnet_id,
                        "Groups": [security_group_id],
                        "InterfaceType": interface_type,
                    }
                )
    else:
        struct["SecurityGroupIds"] = [security_group_id]

    if placement_group_name is not None:
        struct["Placement"] = {
            "GroupName": placement_group_name,
        }

    if reservation_id is not None:
        struct["CapacityReservationSpecification"] = {
            "CapacityReservationTarget": {"CapacityReservationId": reservation_id}
        }

    return struct


def get_gateway_image_id(ec2_client: botocore.client.BaseClient) -> str:
    response = ec2_client.describe_images(
        Filters=[
            {
                "Name": "name",
                "Values": ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"],
            },
            {
                "Name": "owner-alias",
                "Values": ["amazon"],
            },
        ],
    )
    image = sorted(response["Images"], key=lambda i: i["CreationDate"], reverse=True)[0]
    return image["ImageId"]


def create_gateway_security_group(
    ec2_client: botocore.client.BaseClient,
    project_id: str,
    vpc_id: Optional[str],
) -> str:
    security_group_name = "dstack_gw_sg_" + project_id.replace("-", "_").lower()
    describe_security_groups_filters = [
        {
            "Name": "group-name",
            "Values": [security_group_name],
        },
    ]
    if vpc_id is not None:
        describe_security_groups_filters.append(
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            }
        )
    response = ec2_client.describe_security_groups(Filters=describe_security_groups_filters)
    if response.get("SecurityGroups"):
        return response["SecurityGroups"][0]["GroupId"]
    create_security_group_kwargs = {}
    if vpc_id is not None:
        create_security_group_kwargs["VpcId"] = vpc_id
    security_group = ec2_client.create_security_group(
        Description="Generated by dstack",
        GroupName=security_group_name,
        TagSpecifications=[
            {
                "ResourceType": "security-group",
                "Tags": [
                    {"Key": "owner", "Value": "dstack"},
                    {"Key": "role", "Value": "gateway"},
                    {"Key": "dstack_project", "Value": project_id},
                ],
            },
        ],
        **create_security_group_kwargs,
    )
    group_id = security_group["GroupId"]

    ec2_client.authorize_security_group_ingress(
        GroupId=group_id,
        IpPermissions=[
            {
                "FromPort": 22,
                "ToPort": 22,
                "IpProtocol": "tcp",
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            },
            {
                "FromPort": 80,
                "ToPort": 80,
                "IpProtocol": "tcp",
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            },
            {
                "FromPort": 443,
                "ToPort": 443,
                "IpProtocol": "tcp",
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            },
        ],
    )

    ec2_client.authorize_security_group_egress(
        GroupId=group_id,
        IpPermissions=[{"IpProtocol": "-1"}],
    )
    return group_id


def get_vpc_id_by_name(
    ec2_client: botocore.client.BaseClient,
    vpc_name: str,
) -> Optional[str]:
    response = ec2_client.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": [vpc_name]}])
    if len(response["Vpcs"]) == 0:
        return None
    return response["Vpcs"][0]["VpcId"]


def get_default_vpc_id(ec2_client: botocore.client.BaseClient) -> Optional[str]:
    response = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    if "Vpcs" in response and len(response["Vpcs"]) > 0:
        return response["Vpcs"][0]["VpcId"]
    return None


def get_vpc_by_vpc_id(ec2_client: botocore.client.BaseClient, vpc_id: str) -> Optional[str]:
    response = ec2_client.describe_vpcs(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    if "Vpcs" in response and len(response["Vpcs"]) > 0:
        return response["Vpcs"][0]
    return None


def get_subnets_ids_for_vpc(
    ec2_client: botocore.client.BaseClient,
    vpc_id: str,
    allocate_public_ip: bool,
    availability_zones: Optional[List[str]] = None,
) -> List[str]:
    """
    If `allocate_public_ip` is True, returns public subnets found in the VPC.
    If `allocate_public_ip` is False, returns subnets with NAT found in the VPC.
    """
    subnets = _get_subnets_by_vpc_id(
        ec2_client=ec2_client,
        vpc_id=vpc_id,
        availability_zones=availability_zones,
    )
    if len(subnets) == 0:
        return []
    subnets_ids = []
    for subnet in subnets:
        subnet_id = subnet["SubnetId"]
        if allocate_public_ip:
            is_public_subnet = _is_public_subnet(
                ec2_client=ec2_client, vpc_id=vpc_id, subnet_id=subnet_id
            )
            if is_public_subnet:
                subnets_ids.append(subnet_id)
        else:
            is_eligible_private_subnet = _is_private_subnet_with_internet_egress(
                ec2_client=ec2_client,
                vpc_id=vpc_id,
                subnet_id=subnet_id,
            )
            if is_eligible_private_subnet:
                subnets_ids.append(subnet_id)

    return subnets_ids


def get_availability_zone(ec2_client: botocore.client.BaseClient, region: str) -> Optional[str]:
    zone_names = get_availability_zones(
        ec2_client=ec2_client,
        region=region,
    )
    if len(zone_names) == 0:
        return None
    return zone_names[0]


def get_availability_zones(ec2_client: botocore.client.BaseClient, region: str) -> List[str]:
    response = ec2_client.describe_availability_zones(
        Filters=[
            {
                "Name": "region-name",
                "Values": [region],
            }
        ]
    )
    zone_names = [z["ZoneName"] for z in response["AvailabilityZones"]]
    return zone_names


def get_availability_zone_by_subnet_id(
    ec2_client: botocore.client.BaseClient, subnet_id: str
) -> str:
    response = ec2_client.describe_subnets(SubnetIds=[subnet_id])
    return response["Subnets"][0]["AvailabilityZone"]


def get_subnets_availability_zones(
    ec2_client: botocore.client.BaseClient, subnet_ids: List[str]
) -> Dict[str, str]:
    response = ec2_client.describe_subnets(SubnetIds=subnet_ids)
    subnet_id_to_az_map = {
        subnet["SubnetId"]: subnet["AvailabilityZone"] for subnet in response["Subnets"]
    }
    return subnet_id_to_az_map


def list_available_device_names(
    ec2_client: botocore.client.BaseClient, instance_id: str
) -> List[str]:
    device_names = _list_possible_device_names()
    used_device_names = list_instance_device_names(ec2_client, instance_id)
    return [n for n in device_names if n not in used_device_names]


def list_instance_device_names(
    ec2_client: botocore.client.BaseClient, instance_id: str
) -> List[str]:
    device_names = []
    response = ec2_client.describe_instance_attribute(
        InstanceId=instance_id, Attribute="blockDeviceMapping"
    )
    block_device_mappings = response["BlockDeviceMappings"]
    for mapping in block_device_mappings:
        device_names.append(mapping["DeviceName"])
    return device_names


def make_tags(tags: Dict[str, str]) -> List[Dict[str, str]]:
    tags_list = []
    for k, v in tags.items():
        tags_list.append({"Key": k, "Value": v})
    return tags_list


def validate_tags(tags: Dict[str, str]):
    for k, v in tags.items():
        if not _is_valid_tag(k, v):
            raise BackendError(
                "Invalid resource tags. "
                "See tags restrictions: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Using_Tags.html#tag-restrictions"
            )


def _is_valid_tag(key: str, value: str) -> bool:
    return _is_valid_tag_key(key) and _is_valid_tag_value(value)


TAG_KEY_PATTERN = re.compile(r"^[\w .:/=\-+@]{1,128}$")
TAG_VALUE_PATTERN = re.compile(r"^[\w .:/=\-+@]{0,256}$")


def _is_valid_tag_key(key: str) -> bool:
    if key.startswith("aws:"):
        return False
    match = re.match(TAG_KEY_PATTERN, key)
    return match is not None


def _is_valid_tag_value(value: str) -> bool:
    match = re.match(TAG_VALUE_PATTERN, value)
    return match is not None


def _list_possible_device_names() -> List[str]:
    suffixes = ["f", "g", "h", "i", "j", "k", "l", "m", "n"]
    return [f"/dev/sd{s}" for s in suffixes]


def _add_ingress_security_group_rule_if_missing(
    ec2_client: botocore.client.BaseClient,
    security_group: Dict,
    security_group_id: str,
    rule: Dict,
) -> bool:
    if _rule_exists(rule, security_group.get("IpPermissions", [])):
        return False
    ec2_client.authorize_security_group_ingress(
        GroupId=security_group_id,
        IpPermissions=[rule],
    )
    return True


def _add_egress_security_group_rule_if_missing(
    ec2_client: botocore.client.BaseClient,
    security_group: Dict,
    security_group_id: str,
    rule: Dict,
) -> bool:
    if _rule_exists(rule, security_group.get("IpPermissionsEgress", [])):
        return False
    ec2_client.authorize_security_group_egress(
        GroupId=security_group_id,
        IpPermissions=[rule],
    )
    return True


def _rule_exists(rule: Dict, rules: List[Dict]) -> bool:
    """
    Rule exists if there are an existing rule that includes all the keys with the same values.
    Note that the existing rule may have keys missing from the rule.
    """
    return any(_is_subset(rule, other_rule) for other_rule in rules)


def _is_subset(subset, superset) -> bool:
    if isinstance(subset, dict) and isinstance(superset, dict):
        return all(k in superset and _is_subset(v, superset[k]) for k, v in subset.items())
    if isinstance(subset, list) and isinstance(superset, list):
        return len(subset) == len(superset) and all(
            _is_subset(v1, v2) for v1, v2 in zip(subset, superset)
        )
    return subset == superset


def _get_subnets_by_vpc_id(
    ec2_client: botocore.client.BaseClient,
    vpc_id: str,
    availability_zones: Optional[List[str]] = None,
) -> List[Dict]:
    filters = [{"Name": "vpc-id", "Values": [vpc_id]}]
    if availability_zones is not None:
        filters.append({"Name": "availability-zone", "Values": availability_zones})
    response = ec2_client.describe_subnets(Filters=filters)
    return response["Subnets"]


def _is_public_subnet(
    ec2_client: botocore.client.BaseClient,
    vpc_id: str,
    subnet_id: str,
) -> bool:
    # Public subnet – The subnet has a direct route to an internet gateway.
    # Private subnet – The subnet does not have a direct route to an internet gateway.

    # Check explicitly associated route tables
    response = ec2_client.describe_route_tables(
        Filters=[{"Name": "association.subnet-id", "Values": [subnet_id]}]
    )
    for route_table in response["RouteTables"]:
        for route in route_table["Routes"]:
            if "GatewayId" in route and route["GatewayId"].startswith("igw-"):
                return True

    # Main route table controls the routing of all subnetes
    # that are not explicitly associated with any other route table.
    if len(response["RouteTables"]) > 0:
        return False

    # Check implicitly associated main route table
    response = ec2_client.describe_route_tables(
        Filters=[
            {"Name": "association.main", "Values": ["true"]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )
    for route_table in response["RouteTables"]:
        for route in route_table["Routes"]:
            if "GatewayId" in route and route["GatewayId"].startswith("igw-"):
                return True

    return False


_PRIVATE_SUBNET_EGRESS_ROUTE_KEYS = ["NatGatewayId", "TransitGatewayId", "VpcPeeringConnectionId"]


def _is_private_subnet_with_internet_egress(
    ec2_client: botocore.client.BaseClient,
    vpc_id: str,
    subnet_id: str,
) -> bool:
    # Check explicitly associated route tables
    response = ec2_client.describe_route_tables(
        Filters=[{"Name": "association.subnet-id", "Values": [subnet_id]}]
    )
    for route_table in response["RouteTables"]:
        for route in route_table["Routes"]:
            if route.get("DestinationCidrBlock") == "0.0.0.0/0":
                if any(route.get(k) for k in _PRIVATE_SUBNET_EGRESS_ROUTE_KEYS):
                    return True

    # Main route table controls the routing of all subnetes
    # that are not explicitly associated with any other route table.
    if len(response["RouteTables"]) > 0:
        return False

    # Check implicitly associated main route table
    response = ec2_client.describe_route_tables(
        Filters=[
            {"Name": "association.main", "Values": ["true"]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )
    for route_table in response["RouteTables"]:
        for route in route_table["Routes"]:
            if route.get("DestinationCidrBlock") == "0.0.0.0/0":
                if any(route.get(k) for k in _PRIVATE_SUBNET_EGRESS_ROUTE_KEYS):
                    return True

    return False


def get_reservation(
    ec2_client: botocore.client.BaseClient,
    reservation_id: str,
    instance_count: int = 0,
    instance_types: Optional[List[str]] = None,
    is_capacity_block: bool = False,
) -> Optional[Dict[str, Any]]:
    filters = [{"Name": "state", "Values": ["active"]}]
    if instance_types:
        filters.append({"Name": "instance-type", "Values": instance_types})
    try:
        response = ec2_client.describe_capacity_reservations(
            CapacityReservationIds=[reservation_id], Filters=filters
        )
    except botocore.exceptions.ParamValidationError as e:
        logger.debug(
            "Skipping reservation %s. Parameter validation error: %s", reservation_id, repr(e)
        )
        return None
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "InvalidCapacityReservationId.Malformed":
            logger.debug("Skipping reservation %s. Malformed ID.", reservation_id)
            return None
        if error_code == "InvalidCapacityReservationId.NotFound":
            logger.debug(
                "Skipping reservation %s. Capacity Reservation not found.", reservation_id
            )
            return None
        raise
    reservation = response["CapacityReservations"][0]

    if instance_count > 0 and reservation["AvailableInstanceCount"] < instance_count:
        return None

    if is_capacity_block and reservation["ReservationType"] != "capacity-block":
        return None

    return reservation
