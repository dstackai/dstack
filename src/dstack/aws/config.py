import sys

from botocore.client import BaseClient
from rich.prompt import Confirm

from dstack.aws import runners


def configure(iam_client: BaseClient, s3_client: BaseClient, bucket_name: str, region_name: str, silent: bool):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except Exception as e:
        if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "403":
            sys.exit(f"You don't have access the '{bucket_name}' bucket. "
                     "The bucket may belong to another account.")
        else:
            if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "404":
                if silent or Confirm.ask(f"[red]The bucket '{bucket_name}' doesn't exist. Create it?[/]"):
                    if region_name != "us-east-1":
                        s3_client.create_bucket(Bucket=bucket_name,
                                                CreateBucketConfiguration={"LocationConstraint": region_name})
                    else:
                        s3_client.create_bucket(Bucket=bucket_name)
                else:
                    return
            else:
                raise e
    runners.instance_profile_arn(iam_client, bucket_name)

