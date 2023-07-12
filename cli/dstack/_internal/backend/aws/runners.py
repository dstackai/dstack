import json
import time
from functools import reduce
from typing import List, Optional, Tuple

import botocore.exceptions
from boto3 import Session
from botocore.client import BaseClient

from dstack import version
from dstack._internal.backend.aws import utils as aws_utils
from dstack._internal.backend.base.compute import (
    WS_PORT,
    NoCapacityError,
    choose_instance_type,
    get_dstack_runner,
)
from dstack._internal.backend.base.config import BACKEND_CONFIG_FILENAME, RUNNER_CONFIG_FILENAME
from dstack._internal.backend.base.runners import serialize_runner_yaml
from dstack._internal.core.instance import InstanceType, LaunchedInstanceInfo
from dstack._internal.core.job import Job, Requirements
from dstack._internal.core.request import RequestHead, RequestStatus
from dstack._internal.core.runners import Gpu, Resources
from dstack._internal.utils import logging

CREATE_INSTANCE_RETRY_RATE_SECS = 3


logger = logging.get_logger(__name__)


def get_instance_type(
    ec2_client: BaseClient, requirements: Optional[Requirements]
) -> Optional[InstanceType]:
    instance_types = _get_instance_types(ec2_client)
    return choose_instance_type(instance_types, requirements)


def run_instance(
    session: Session,
    iam_client: BaseClient,
    bucket_name: str,
    region_name: str,
    extra_regions: List[str],
    subnet_id: Optional[str],
    runner_id: str,
    instance_type: InstanceType,
    spot: bool,
    repo_id: str,
    hub_user_name: str,
    ssh_key_pub: str,
) -> LaunchedInstanceInfo:
    regions = [region_name]
    if extra_regions:
        regions.extend(
            _get_instance_available_regions(
                ec2_client=aws_utils.get_ec2_client(session),
                instance_type=instance_type,
                extra_regions=extra_regions,
            )
        )
    for region in regions:
        try:
            logger.info(
                "Requesting %s %s instance in %s...",
                instance_type.instance_name,
                "spot" if spot else "",
                region,
            )
            request_id = _run_instance_retry(
                ec2_client=aws_utils.get_ec2_client(session, region_name=region),
                iam_client=iam_client,
                bucket_name=bucket_name,
                region_name=region,
                subnet_id=subnet_id,
                runner_id=runner_id,
                instance_type=instance_type,
                spot=spot,
                repo_id=repo_id,
                hub_user_name=hub_user_name,
                ssh_key_pub=ssh_key_pub,
            )
            logger.info("Request succeeded")
            return LaunchedInstanceInfo(request_id=request_id, location=region)
        except NoCapacityError:
            logger.info("Failed to request instance in %s", region)
    logger.info("Failed to request instance")
    raise NoCapacityError()


def cancel_spot_request(ec2_client: BaseClient, request_id: str):
    try:
        ec2_client.cancel_spot_instance_requests(SpotInstanceRequestIds=[request_id])
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "InvalidSpotInstanceRequestID.NotFound":
            return
        else:
            raise e
    response = ec2_client.describe_instances(
        Filters=[
            {"Name": "spot-instance-request-id", "Values": [request_id]},
        ],
    )
    if response.get("Reservations") and response["Reservations"][0].get("Instances"):
        ec2_client.terminate_instances(
            InstanceIds=[response["Reservations"][0]["Instances"][0]["InstanceId"]]
        )


def terminate_instance(ec2_client: BaseClient, request_id: str):
    try:
        ec2_client.terminate_instances(InstanceIds=[request_id])
    except Exception as e:
        if (
            hasattr(e, "response")
            and e.response.get("Error")
            and e.response["Error"].get("Code") == "InvalidInstanceID.NotFound"
        ):
            pass
        else:
            raise e


def get_request_head(
    ec2_client: BaseClient,
    job: Job,
    request_id: Optional[str],
) -> RequestHead:
    spot = job.requirements.spot
    if request_id is None:
        message = (
            "The spot instance request ID is not specified"
            if spot
            else "The instance ID is not specified"
        )
        return RequestHead(job_id=job.job_id, status=RequestStatus.TERMINATED, message=message)

    if spot:
        try:
            response = ec2_client.describe_spot_instance_requests(
                SpotInstanceRequestIds=[request_id]
            )
            if response.get("SpotInstanceRequests"):
                status = response["SpotInstanceRequests"][0]["Status"]
                if status["Code"] in [
                    "fulfilled",
                    "request-canceled-and-instance-running",
                    "marked-for-stop-by-experiment",
                    "marked-for-stop",
                    "marked-for-termination",
                ]:
                    request_status = RequestStatus.RUNNING
                elif status["Code"] in [
                    "not-scheduled-yet",
                    "pending-evaluation",
                    "pending-fulfillment",
                ]:
                    request_status = RequestStatus.PENDING
                elif status["Code"] in [
                    "capacity-not-available",
                    "instance-stopped-no-capacity",
                    "instance-terminated-by-price",
                    "instance-stopped-by-price",
                    "instance-terminated-no-capacity",
                    "instance-stopped-by-experiment",
                    "instance-terminated-by-experiment",
                    "limit-exceeded",
                    "price-too-low",
                ]:
                    request_status = RequestStatus.NO_CAPACITY
                elif status["Code"] in [
                    "instance-terminated-by-user",
                    "instance-stopped-by-user",
                    "canceled-before-fulfillment",
                    "instance-terminated-by-schedule",
                    "instance-terminated-by-service",
                    "spot-instance-terminated-by-user",
                ]:
                    request_status = RequestStatus.TERMINATED
                else:
                    raise Exception(
                        f"Unsupported EC2 spot instance request status code: {status['Code']}"
                    )
                return RequestHead(
                    job_id=job.job_id, status=request_status, message=status.get("Message")
                )
            else:
                return RequestHead(
                    job_id=job.job_id, status=RequestStatus.TERMINATED, message=None
                )
        except Exception as e:
            if (
                hasattr(e, "response")
                and e.response.get("Error")
                and e.response["Error"].get("Code") == "InvalidSpotInstanceRequestID.NotFound"
            ):
                return RequestHead(
                    job_id=job.job_id,
                    status=RequestStatus.TERMINATED,
                    message=e.response["Error"].get("Message"),
                )
            else:
                raise e
    else:
        try:
            response = ec2_client.describe_instances(InstanceIds=[request_id])
            if response.get("Reservations") and response["Reservations"][0].get("Instances"):
                state = response["Reservations"][0]["Instances"][0]["State"]
                if state["Name"] in ["running"]:
                    request_status = RequestStatus.RUNNING
                elif state["Name"] in ["pending"]:
                    request_status = RequestStatus.PENDING
                elif state["Name"] in [
                    "shutting-down",
                    "terminated",
                    "stopping",
                    "stopped",
                ]:
                    request_status = RequestStatus.TERMINATED
                else:
                    raise Exception(f"Unsupported EC2 instance state name: {state['Name']}")
                return RequestHead(job_id=job.job_id, status=request_status, message=None)
            else:
                return RequestHead(
                    job_id=job.job_id, status=RequestStatus.TERMINATED, message=None
                )
        except Exception as e:
            if (
                hasattr(e, "response")
                and e.response.get("Error")
                and e.response["Error"].get("Code") == "InvalidInstanceID.NotFound"
            ):
                return RequestHead(
                    job_id=job.job_id,
                    status=RequestStatus.TERMINATED,
                    message=e.response["Error"].get("Message"),
                )
            else:
                raise e


def _get_instance_types(ec2_client: BaseClient) -> List[InstanceType]:
    response = None
    instance_types = []
    while not response or response.get("NextToken"):
        kwargs = {}
        if response and "NextToken" in response:
            kwargs["NextToken"] = response["NextToken"]
        response = ec2_client.describe_instance_types(
            Filters=[
                {
                    "Name": "instance-type",
                    "Values": [
                        "t2.small",
                        "c5.*",
                        "m5.*",
                        "p2.*",
                        "p3.*",
                        "g5.*",
                        "g4dn.*",
                        "p4d.*",
                        "p4de.*",
                    ],
                },
            ],
            **kwargs,
        )
        for instance_type in response["InstanceTypes"]:
            gpus = (
                [
                    [Gpu(name=gpu["Name"], memory_mib=gpu["MemoryInfo"]["SizeInMiB"])]
                    * gpu["Count"]
                    for gpu in instance_type["GpuInfo"]["Gpus"]
                ]
                if instance_type.get("GpuInfo") and instance_type["GpuInfo"].get("Gpus")
                else []
            )
            instance_types.append(
                InstanceType(
                    instance_name=instance_type["InstanceType"],
                    resources=Resources(
                        cpus=instance_type["VCpuInfo"]["DefaultVCpus"],
                        memory_mib=instance_type["MemoryInfo"]["SizeInMiB"],
                        gpus=reduce(list.__add__, gpus) if gpus else [],
                        spot="spot" in instance_type["SupportedUsageClasses"],
                        local=False,
                    ),
                )
            )
    return instance_types


def _get_instance_available_regions(
    ec2_client: BaseClient,
    instance_type: InstanceType,
    extra_regions: List[str],
) -> List[str]:
    resp = ec2_client.get_spot_placement_scores(
        InstanceTypes=[instance_type.instance_name],
        TargetCapacity=1,
        RegionNames=extra_regions,
    )
    spot_scores = resp["SpotPlacementScores"]
    spot_scores = sorted(spot_scores, key=lambda x: -x["Score"])
    return [s["Region"] for s in spot_scores]


def _run_instance_retry(
    ec2_client: BaseClient,
    iam_client: BaseClient,
    bucket_name: str,
    region_name: str,
    subnet_id: Optional[str],
    runner_id: str,
    instance_type: InstanceType,
    spot: bool,
    repo_id: str,
    hub_user_name: str,
    ssh_key_pub: str,
    attempts: int = 3,
) -> str:
    try:
        return _run_instance(
            ec2_client,
            iam_client,
            bucket_name,
            region_name,
            subnet_id,
            runner_id,
            instance_type,
            spot,
            repo_id,
            hub_user_name,
            ssh_key_pub,
        )
    except botocore.exceptions.ClientError as e:
        # FIXME: why retry on "InvalidParameterValue"
        if e.response["Error"]["Code"] == "InvalidParameterValue":
            if attempts > 0:
                time.sleep(CREATE_INSTANCE_RETRY_RATE_SECS)
                return _run_instance_retry(
                    ec2_client,
                    iam_client,
                    bucket_name,
                    region_name,
                    subnet_id,
                    runner_id,
                    instance_type,
                    spot,
                    repo_id,
                    hub_user_name,
                    ssh_key_pub,
                    attempts - 1,
                )
            else:
                raise Exception("Failed to retry", e)
        elif e.response["Error"]["Code"] == "InsufficientInstanceCapacity":
            raise NoCapacityError()
        raise e


def _run_instance(
    ec2_client: BaseClient,
    iam_client: BaseClient,
    bucket_name: str,
    region_name: str,
    subnet_id: Optional[str],
    runner_id: str,
    instance_type: InstanceType,
    spot: bool,
    repo_id: str,
    hub_user_name: str,
    ssh_key_pub: str,
) -> str:
    launch_specification = {}
    if spot:
        launch_specification["InstanceMarketOptions"] = {
            "MarketType": "spot",
            "SpotOptions": {
                "SpotInstanceType": "one-time",
                "InstanceInterruptionBehavior": "terminate",
            },
        }
    if subnet_id:
        launch_specification["NetworkInterfaces"] = [
            {
                "AssociatePublicIpAddress": True,
                "DeviceIndex": 0,
                "SubnetId": subnet_id,
                "Groups": [_get_security_group_id(ec2_client, bucket_name, subnet_id)],
            },
        ]
    else:
        launch_specification["SecurityGroupIds"] = [
            _get_security_group_id(ec2_client, bucket_name, subnet_id)
        ]
    tags = [
        {"Key": "owner", "Value": "dstack"},
        {"Key": "dstack_bucket", "Value": bucket_name},
        {"Key": "dstack_repo", "Value": repo_id},
        {"Key": "dstack_repo_user", "Value": hub_user_name},
    ]
    response = ec2_client.run_instances(
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": 100,
                    "VolumeType": "gp2",
                },
            }
        ],
        ImageId=_get_ami_image(ec2_client, len(instance_type.resources.gpus) > 0)[0],
        InstanceType=instance_type.instance_name,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={
            "Arn": _get_instance_profile_arn(iam_client, bucket_name),
        },
        UserData=_user_data(
            bucket_name, region_name, runner_id, instance_type.resources, ssh_key_pub=ssh_key_pub
        ),
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": tags,
            },
        ],
        **launch_specification,
    )
    if spot:
        request_id = response["Instances"][0]["SpotInstanceRequestId"]
        ec2_client.create_tags(Resources=[request_id], Tags=tags)
    else:
        request_id = response["Instances"][0]["InstanceId"]
    return request_id


def _user_data(
    bucket_name,
    region_name,
    runner_id: str,
    resources: Resources,
    ssh_key_pub: str,
    port_range_from: int = 3000,
    port_range_to: int = 4000,
) -> str:
    sysctl_port_range_from = int((port_range_to - port_range_from) / 2) + port_range_from
    sysctl_port_range_to = port_range_to - 1
    runner_port_range_from = port_range_from
    runner_port_range_to = sysctl_port_range_from - 1
    user_data = f"""#!/bin/bash
if [ -e "/etc/fuse.conf" ]
then
sudo sed "s/# *user_allow_other/user_allow_other/" /etc/fuse.conf > t
sudo mv t /etc/fuse.conf
else
echo "user_allow_other" | sudo tee -a /etc/fuse.conf > /dev/null
fi
sudo sysctl -w net.ipv4.ip_local_port_range="{sysctl_port_range_from} ${sysctl_port_range_to}"
mkdir -p /root/.dstack/
echo $'{_serialize_config_yaml(bucket_name, region_name)}' > /root/.dstack/{BACKEND_CONFIG_FILENAME}
echo $'{serialize_runner_yaml(runner_id, resources, runner_port_range_from, runner_port_range_to)}' > /root/.dstack/{RUNNER_CONFIG_FILENAME}
die() {{ status=$1; shift; echo "FATAL: $*"; exit $status; }}
EC2_PUBLIC_HOSTNAME="`wget -q -O - http://169.254.169.254/latest/meta-data/public-hostname || die \"wget public-hostname has failed: $?\"`"
echo "hostname: $EC2_PUBLIC_HOSTNAME" >> /root/.dstack/{RUNNER_CONFIG_FILENAME}
mkdir ~/.ssh; chmod 700 ~/.ssh; echo "{ssh_key_pub}" > ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys
{get_dstack_runner()}
HOME=/root nohup dstack-runner --log-level 6 start --http-port {WS_PORT} &
"""
    return user_data


def _serialize_config_yaml(bucket_name: str, region_name: str):
    return f"backend: aws\\n" f"bucket: {bucket_name}\\n" f"region: {region_name}"


def _get_security_group_id(ec2_client: BaseClient, bucket_name: str, subnet_id: Optional[str]):
    _subnet_postfix = (subnet_id.replace("-", "_") + "_") if subnet_id else ""
    security_group_name = (
        "dstack_security_group_" + _subnet_postfix + bucket_name.replace("-", "_").lower()
    )
    if not version.__is_release__:
        security_group_name += "_stgn"
    response = ec2_client.describe_security_groups(
        Filters=[
            {
                "Name": "group-name",
                "Values": [
                    security_group_name,
                ],
            },
        ],
    )
    if response.get("SecurityGroups"):
        security_group_id = response["SecurityGroups"][0]["GroupId"]
    else:
        group_specification = {}
        if subnet_id:
            subnets_response = ec2_client.describe_subnets(SubnetIds=[subnet_id])
            group_specification["VpcId"] = subnets_response["Subnets"][0]["VpcId"]
        security_group = ec2_client.create_security_group(
            Description="Generated by dstack",
            GroupName=security_group_name,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [
                        {"Key": "owner", "Value": "dstack"},
                        {"Key": "dstack_bucket", "Value": bucket_name},
                    ],
                },
            ],
            **group_specification,
        )
        security_group_id = security_group["GroupId"]
        ip_permissions = [
            {
                "FromPort": 22,
                "ToPort": 22,
                "IpProtocol": "tcp",
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }
        ]
        ec2_client.authorize_security_group_ingress(
            GroupId=security_group_id, IpPermissions=ip_permissions
        )
        ec2_client.authorize_security_group_egress(
            GroupId=security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "-1",
                }
            ],
        )
    return security_group_id


def _get_instance_profile_arn(iam_client: BaseClient, bucket_name: str) -> str:
    _role_name = _get_role_name(iam_client, bucket_name)
    try:
        response = iam_client.get_instance_profile(InstanceProfileName=_role_name)
        return response["InstanceProfile"]["Arn"]
    except Exception as e:
        if (
            hasattr(e, "response")
            and e.response.get("Error")
            and e.response["Error"].get("Code") == "NoSuchEntity"
        ):
            response = iam_client.create_instance_profile(
                InstanceProfileName=_role_name,
                Tags=[
                    {"Key": "owner", "Value": "dstack"},
                    {"Key": "dstack_bucket", "Value": bucket_name},
                ],
            )
            _instance_profile_arn = response["InstanceProfile"]["Arn"]
            iam_client.add_role_to_instance_profile(
                InstanceProfileName=_role_name,
                RoleName=_role_name,
            )
            return _instance_profile_arn
        else:
            raise e


def _get_role_name(iam_client: BaseClient, bucket_name: str) -> str:
    policy_name = "dstack_policy_" + bucket_name.replace("-", "_").lower()
    _role_name = "dstack_role_" + bucket_name.replace("-", "_").lower()
    try:
        iam_client.get_role(RoleName=_role_name)
    except Exception as e:
        if (
            hasattr(e, "response")
            and e.response.get("Error")
            and e.response["Error"].get("Code") == "NoSuchEntity"
        ):
            response = iam_client.create_policy(
                PolicyName=policy_name,
                Description="Generated by dstack",
                PolicyDocument=json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "s3:*",
                                "Resource": [
                                    f"arn:aws:s3:::{bucket_name}",
                                    f"arn:aws:s3:::{bucket_name}/*",
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": "logs:*",
                                "Resource": [
                                    f"arn:aws:logs:*:*:log-group:/dstack/jobs/{bucket_name}*:*",
                                    f"arn:aws:logs:*:*:log-group:/dstack/runners/{bucket_name}*:*",
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": "ec2:*",
                                "Resource": "*",
                                "Condition": {
                                    "StringEquals": {
                                        "aws:ResourceTag/dstack_bucket": bucket_name,
                                    }
                                },
                            },
                        ],
                    }
                ),
                Tags=[
                    {"Key": "owner", "Value": "dstack"},
                    {"Key": "dstack_bucket", "Value": bucket_name},
                ],
            )
            policy_arn = response["Policy"]["Arn"]
            iam_client.create_role(
                RoleName=_role_name,
                AssumeRolePolicyDocument=json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Action": "sts:AssumeRole",
                                "Effect": "Allow",
                                "Principal": {"Service": "ec2.amazonaws.com"},
                            }
                        ],
                    }
                ),
                Description="Generated by dstack",
                MaxSessionDuration=3600,
                Tags=[
                    {"Key": "owner", "Value": "dstack"},
                    {"Key": "dstack_bucket", "Value": bucket_name},
                ],
            )
            iam_client.attach_role_policy(RoleName=_role_name, PolicyArn=policy_arn)
        else:
            raise e
    return _role_name


def _get_default_ami_image_version() -> Optional[str]:
    if version.__is_release__:
        return version.__version__
    else:
        return None


def _get_ami_image(
    ec2_client: BaseClient,
    cuda: bool,
    _version: Optional[str] = _get_default_ami_image_version(),
) -> Tuple[str, str]:
    ami_name = "dstack"
    if cuda:
        ami_name = ami_name + "-cuda-11.4"
    if not version.__is_release__:
        ami_name = "[stgn] " + ami_name
    ami_name = ami_name + f"-{_version or '*'}"
    response = ec2_client.describe_images(
        Filters=[
            {"Name": "name", "Values": [ami_name]},
        ],
    )
    images = list(
        filter(
            lambda i: cuda == ("cuda" in i["Name"]) and i["State"] == "available",
            response["Images"],
        )
    )
    if images:
        ami = next(iter(sorted(images, key=lambda i: i["CreationDate"], reverse=True)))
        return ami["ImageId"], ami["Name"]
    else:
        if _version:
            return _get_ami_image(ec2_client, cuda, _version=None)
        else:
            raise Exception(f"Can't find an AMI image prefix={ami_name!r}")
