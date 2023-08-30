from typing import List, Optional

from boto3 import Session

import dstack._internal.backend.aws.gateway as gateway
from dstack._internal.backend.aws import runners
from dstack._internal.backend.aws import utils as aws_utils
from dstack._internal.backend.aws.config import AWSConfig
from dstack._internal.backend.base.compute import Compute
from dstack._internal.core.gateway import GatewayHead
from dstack._internal.core.instance import InstanceType, LaunchedInstanceInfo
from dstack._internal.core.job import Job
from dstack._internal.core.request import RequestHead
from dstack._internal.core.runners import Runner


class AWSCompute(Compute):
    def __init__(
        self,
        session: Session,
        backend_config: AWSConfig,
    ):
        self.session = session
        self.iam_client = aws_utils.get_iam_client(session)
        self.backend_config = backend_config

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        return runners.get_request_head(
            ec2_client=self._get_ec2_client(region=job.location),
            job=job,
            request_id=request_id,
        )

    # TODO: This function is deprecated and will be deleted in 0.11.x
    def get_instance_type(self, job: Job, region_name: Optional[str]) -> Optional[InstanceType]:
        return runners.get_instance_type(
            ec2_client=self._get_ec2_client(region_name),
            requirements=job.requirements,
        )

    def get_supported_instances(self) -> List[InstanceType]:
        instances = {}
        for region in self.backend_config.regions:
            for i in runners._get_instance_types(self._get_ec2_client(region=region)):
                if i.instance_name not in instances:
                    instances[i.instance_name] = i
                    i.available_regions = []
                instances[i.instance_name].available_regions.append(region)
        return list(instances.values())

    def run_instance(
        self, job: Job, instance_type: InstanceType, region: str
    ) -> LaunchedInstanceInfo:
        return runners.run_instance(
            session=self.session,
            iam_client=self.iam_client,
            bucket_name=self.backend_config.bucket_name,
            region_name=region,
            subnet_id=self.backend_config.subnet_id,
            runner_id=job.runner_id,
            instance_type=instance_type,
            spot=job.requirements.spot,
            instance_name=job.instance_name,
            repo_id=job.repo_ref.repo_id,
            hub_user_name=job.hub_user_name,
            ssh_key_pub=job.ssh_key_pub,
        )

    def terminate_instance(self, runner: Runner):
        runners.terminate_instance(
            ec2_client=self._get_ec2_client(region=runner.job.location),
            request_id=runner.request_id,
        )

    def cancel_spot_request(self, runner: Runner):
        runners.cancel_spot_request(
            ec2_client=self._get_ec2_client(region=runner.job.location),
            request_id=runner.request_id,
        )

    def create_gateway(self, instance_name: str, ssh_key_pub: str, region: str) -> GatewayHead:
        instance = gateway.create_gateway_instance(
            ec2_client=self._get_ec2_client(region=region),
            subnet_id=self.backend_config.subnet_id,
            bucket_name=self.backend_config.bucket_name,
            instance_name=instance_name,
            ssh_key_pub=ssh_key_pub,
        )
        return GatewayHead(
            instance_name=instance_name,
            external_ip=instance["PublicIpAddress"],
            internal_ip=instance["PrivateIpAddress"],
            region=region,
        )

    # TODO: Must be renamed to `delete_gateway_instance`
    def delete_instance(self, instance_name: str, region: str = None):
        region = region or self.backend_config.regions[0]
        try:
            instance_id = gateway.get_instance_id(
                ec2_client=self._get_ec2_client(region=region),
                instance_name=instance_name,
            )
            runners.terminate_instance(
                ec2_client=self._get_ec2_client(region=region),
                request_id=instance_id,
            )
        except IndexError:
            return

    def _get_ec2_client(self, region: Optional[str] = None):
        if region is None:
            return aws_utils.get_ec2_client(self.session)
        return aws_utils.get_ec2_client(self.session, region_name=region)
