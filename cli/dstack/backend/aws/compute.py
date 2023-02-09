from typing import Optional, Tuple

from botocore.client import BaseClient

from dstack.backend.aws import runners
from dstack.backend.base.compute import Compute
from dstack.core.instance import InstanceType
from dstack.core.job import Job, Requirements
from dstack.core.request import RequestHead


class AWSCompute(Compute):
    def __init__(
        self,
        ec2_client: BaseClient,
        iam_client: BaseClient,
        bucket_name: str,
        region_name: str,
        subnet_id: str,
    ):
        self.ec2_client = ec2_client
        self.iam_client = iam_client
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.subnet_id = subnet_id

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        return runners.get_request_head(
            ec2_client=self.ec2_client,
            job=job,
            request_id=request_id,
        )

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        return runners._get_instance_type(
            ec2_client=self.ec2_client,
            requirements=job.requirements,
        )

    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        return runners._run_instance_retry(
            ec2_client=self.ec2_client,
            iam_client=self.iam_client,
            bucket_name=self.bucket_name,
            region_name=self.region_name,
            subnet_id=self.subnet_id,
            runner_id=job.runner_id,
            instance_type=instance_type,
            local_repo_user_name=job.local_repo_user_name,
            local_repo_user_email=job.local_repo_user_email,
            repo_address=job.repo_address,
        )

    def terminate_instance(self, request_id: str):
        runners._terminate_instance(
            ec2_client=self.ec2_client,
            request_id=request_id,
        )

    def cancel_spot_request(self, request_id: str):
        runners._cancel_spot_request(
            ec2_client=self.ec2_client,
            request_id=request_id,
        )
