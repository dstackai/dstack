import os
from typing import Dict, Optional

from dstack.backend.base.config import BackendConfig

_DEFAULT_REGION_NAME = "us-east-1"


class AWSConfig(BackendConfig):
    bucket_name = None
    region_name = None
    profile_name = None
    subnet_id = None
    credentials = None

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region_name: Optional[str] = None,
        profile_name: Optional[str] = None,
        subnet_id: Optional[str] = None,
        credentials: Optional[Dict] = None,
    ):
        self.bucket_name = bucket_name or os.getenv("DSTACK_AWS_S3_BUCKET")
        self.region_name = (
            region_name
            or os.getenv("DSTACK_AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or _DEFAULT_REGION_NAME
        )
        self.profile_name = (
            profile_name or os.getenv("DSTACK_AWS_PROFILE") or os.getenv("AWS_PROFILE")
        )
        self.subnet_id = subnet_id or os.getenv("DSTACK_AWS_EC2_SUBNET")
        self.credentials = credentials

    def serialize(self) -> Dict:
        config_data = {
            "backend": "aws",
            "bucket": self.bucket_name,
        }
        if self.region_name:
            config_data["region"] = self.region_name
        if self.profile_name:
            config_data["profile"] = self.profile_name
        if self.subnet_id:
            config_data["subnet"] = self.subnet_id
        return config_data

    @classmethod
    def deserialize(cls, config_data: Dict, auth_data: Dict = None) -> Optional["AWSConfig"]:
        bucket_name = config_data.get("bucket_name") or config_data.get("s3_bucket_name")
        region_name = config_data.get("region_name") or _DEFAULT_REGION_NAME
        profile_name = config_data.get("profile_name")
        subnet_id = (
            config_data.get("subnet_id")
            or config_data.get("ec2_subnet_id")
            or config_data.get("subnet")
        )
        return cls(
            bucket_name=bucket_name,
            region_name=region_name,
            profile_name=profile_name,
            subnet_id=subnet_id,
            credentials=auth_data,
        )
