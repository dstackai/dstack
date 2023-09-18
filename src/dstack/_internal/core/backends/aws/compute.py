from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import boto3
import botocore.client
import botocore.exceptions

import dstack._internal.core.backends.aws.resources as aws_resources
from dstack._internal.core.backends.aws.config import AWSConfig
from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.models.backends.aws import AWSAccessKeyCreds
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceState,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.core.services.offers import get_catalog_offers


class AWSCompute(Compute):
    def __init__(self, config: AWSConfig):
        self.config = config
        if isinstance(config.creds, AWSAccessKeyCreds):
            self.session = boto3.Session(
                aws_access_key_id=config.creds.access_key,
                aws_secret_access_key=config.creds.secret_key,
            )
        else:  # default creds
            self.session = boto3.Session()

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            "aws", set(self.config.regions), requirements, extra_filter=_supported_instances
        )
        regions = set(i.region for i in offers)

        def get_quotas(client: botocore.client.BaseClient) -> Dict[str, int]:
            region_quotas = {}
            for page in client.get_paginator("list_service_quotas").paginate(ServiceCode="ec2"):
                for q in page["Quotas"]:
                    if "On-Demand" in q["QuotaName"]:
                        region_quotas[q["UsageMetric"]["MetricDimensions"]["Class"]] = q["Value"]
            return region_quotas

        quotas = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_region = {}
            for region in regions:
                future = executor.submit(
                    get_quotas, self.session.client("service-quotas", region_name=region)
                )
                future_to_region[future] = region
            for future in as_completed(future_to_region):
                quotas[future_to_region[future]] = future.result()

        availability_offers = []
        for offer in offers:
            availability = InstanceAvailability.UNKNOWN
            if not _has_quota(quotas[offer.region], offer.instance.name):
                availability = InstanceAvailability.NO_QUOTA
            availability_offers.append(
                InstanceOfferWithAvailability(**offer.dict(), availability=availability)
            )
        return availability_offers

    def get_instance_state(self, instance_id: str, region: str) -> InstanceState:
        client = self.session.client("ec2", region_name=region)
        try:
            response = client.describe_instances(InstanceIds=[instance_id])
            state = response["Reservations"][0]["Instances"][0]["State"]["Name"]
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                return InstanceState.NOT_FOUND
            else:
                raise e
        return {
            "pending": InstanceState.PROVISIONING,
            "running": InstanceState.RUNNING,
            "shutting-down": InstanceState.STOPPING,
            "terminated": InstanceState.TERMINATED,
            "stopping": InstanceState.STOPPING,
            "stopped": InstanceState.STOPPED,
        }[state]

    def terminate_instance(self, instance_id: str, region: str):
        client = self.session.client("ec2", region_name=region)
        try:
            client.terminate_instances(InstanceIds=[instance_id])
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                raise  # TODO raise not found
            else:
                raise e

    def run_job(
        self, run: Run, job: Job, instance_offer: InstanceOfferWithAvailability
    ) -> LaunchedInstanceInfo:
        project_id = run.project_name  # TODO unique id
        ec2_client = self.session.client("ec2", region_name=instance_offer.region)
        iam_client = self.session.client("iam", region_name=instance_offer.region)

        tags = [
            {"Key": "Name", "Value": run.run_spec.run_name},
            {"Key": "owner", "Value": "dstack"},
            {"Key": "dstack_project", "Value": project_id},
            {"Key": "dstack_user", "Value": run.user},
            {"Key": "dstack_run", "Value": run.id.hex},
        ]
        try:
            response = ec2_client.run_instances(
                BlockDeviceMappings=[
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": 100,  # TODO run.run_spec.profile.resources.disk_size
                            "VolumeType": "gp2",
                        },
                    }
                ],
                ImageId=aws_resources.get_image_id(
                    ec2_client, len(instance_offer.instance.resources.gpus) > 0
                ),
                InstanceType=instance_offer.instance.name,
                MinCount=1,
                MaxCount=1,
                IamInstanceProfile={
                    "Arn": aws_resources.create_iam_instance_profile(iam_client, project_id),
                },
                UserData=aws_resources.get_user_data(
                    run.run_spec.configuration.image,
                    run.run_spec.ssh_key_pub.strip().split("\n"),
                ),
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": tags,
                    },
                ],
                SecurityGroupIds=[aws_resources.create_security_group(ec2_client, project_id)],
                **aws_resources.get_spot_options(instance_offer.instance.resources.spot),
            )
            if instance_offer.instance.resources.spot:  # it will not terminate the instance
                ec2_client.cancel_spot_instance_requests(
                    SpotInstanceRequestIds=[response["Instances"][0]["SpotInstanceRequestId"]]
                )
            return LaunchedInstanceInfo(
                instance_id=response["Instances"][0]["InstanceId"],
                region=instance_offer.region,
            )
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "InsufficientInstanceCapacity":
                raise  # TODO raise NoCapacity
            raise e


def _has_quota(quotas: Dict[str, float], instance_name: str) -> bool:
    if instance_name.startswith("p"):
        return quotas.get("P/OnDemand", 0) > 0
    if instance_name.startswith("g"):
        return quotas.get("G/OnDemand", 0) > 0
    return quotas.get("Standard/OnDemand", 0) > 0


def _supported_instances(offer: InstanceOffer) -> bool:
    for family in ["t2.small", "c5.", "m5.", "p3.", "g5.", "g4dn.", "p4d.", "p4de."]:
        if offer.instance.name.startswith(family):
            return True
    return False
