from typing import Optional

from botocore.client import BaseClient
from rich import print
from rich.prompt import Confirm

from dstack.aws import runners


def validate_bucket(s3_client: BaseClient, bucket_name: str, region_name: str) -> bool:
    try:
        response = s3_client.head_bucket(Bucket=bucket_name)
        bucket_region = response["ResponseMetadata"]["HTTPHeaders"]["x-amz-bucket-region"]
        if bucket_region != region_name:
            print(f"[red bold]✗[/red bold] [red]The bucket belongs to another AWS region.")
            return False
    except Exception as e:
        if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "403":
            print(f"[red bold]✗[/red bold] [red]You don't have access to this bucket. "
                  "It may belong to another AWS account.[/red]")
            return False
        else:
            if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "404":
                if Confirm.ask(f"[sea_green3 bold]?[/sea_green3 bold] "
                               f"[red bold]The bucket doesn't exist. Create it?[/red bold]"):
                    if region_name != "us-east-1":
                        s3_client.create_bucket(Bucket=bucket_name,
                                                CreateBucketConfiguration={"LocationConstraint": region_name})
                    else:
                        s3_client.create_bucket(Bucket=bucket_name)
                else:
                    return False
            else:
                raise e
    return True


def configure(ec2_client: BaseClient, iam_client: BaseClient, bucket_name: str, subnet_id: Optional[str]):
    runners.instance_profile_arn(iam_client, bucket_name)
    runners.get_security_group_id(ec2_client, bucket_name, subnet_id)
