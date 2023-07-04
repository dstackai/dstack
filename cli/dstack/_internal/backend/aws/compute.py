from typing import Optional

from boto3 import Session

from dstack._internal.backend.aws import runners
from dstack._internal.backend.aws import utils as aws_utils
from dstack._internal.backend.aws.config import AWSConfig
from dstack._internal.backend.base.compute import Compute
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

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        return runners.get_instance_type(
            ec2_client=self._get_ec2_client(),
            requirements=job.requirements,
        )

    def run_instance(self, job: Job, instance_type: InstanceType) -> LaunchedInstanceInfo:
        return runners.run_instance(
            session=self.session,
            iam_client=self.iam_client,
            bucket_name=self.backend_config.bucket_name,
            region_name=self.backend_config.region_name,
            extra_regions=self.backend_config.extra_regions,
            subnet_id=self.backend_config.subnet_id,
            runner_id=job.runner_id,
            instance_type=instance_type,
            spot=job.requirements.spot,
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

    def _get_ec2_client(self, region: Optional[str] = None):
        if region is None:
            return aws_utils.get_ec2_client(self.session)
        return aws_utils.get_ec2_client(self.session, region_name=region)
