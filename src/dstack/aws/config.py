from botocore.client import BaseClient
from rich.prompt import Confirm

from dstack.aws import runners


def configure(iam_client: BaseClient, s3_client: BaseClient, bucket_name: str, region_name: str, silent: bool):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except Exception as e:
        if silent or Confirm.ask(f"[red]The bucket '{bucket_name}' doesn't exist. Create it?[/]"):
            s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={
                "LocationConstraint": region_name
            })
        else:
            return
    runners.instance_profile_arn(iam_client, bucket_name)

