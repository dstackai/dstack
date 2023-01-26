from typing import Optional

from botocore.client import BaseClient

from dstack.backend.aws import runners


def configure(ec2_client: BaseClient, iam_client: BaseClient, bucket_name: str, subnet_id: Optional[str]):
    runners.instance_profile_arn(iam_client, bucket_name)
    runners.get_security_group_id(ec2_client, bucket_name, subnet_id)
