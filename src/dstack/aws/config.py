import sys

from botocore.client import BaseClient
from rich.prompt import Confirm
from rich import print

from dstack.aws import runners


def configure(iam_client: BaseClient, s3_client: BaseClient, bucket_name: str, region_name: str, silent: bool):
    try:
        response = s3_client.head_bucket(Bucket=bucket_name)
        bucket_region = response["ResponseMetadata"]["HTTPHeaders"]["x-amz-bucket-region"]
        if bucket_region != region_name:
            print(f"[red]Warning! The bucket '{bucket_name}' is in the '{bucket_region}' region "
                  f"while you've configured the '{region_name}' region for dstack.\n"
                  f"The region of the bucket and the region configured for dstack must be the same.")
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

