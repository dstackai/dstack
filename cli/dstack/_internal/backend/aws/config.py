from typing import Dict, List, Optional

from pydantic import BaseModel

from dstack._internal.backend.base.config import BackendConfig

DEFAULT_REGION_NAME = "us-east-1"


class AWSConfig(BackendConfig, BaseModel):
    bucket_name: str
    region_name: Optional[str] = DEFAULT_REGION_NAME
    extra_regions: List[str] = []
    subnet_id: Optional[str] = None
    credentials: Optional[Dict] = None

    def serialize(self) -> Dict:
        config_data = {
            "backend": "aws",
            "bucket": self.bucket_name,
        }
        if self.region_name:
            config_data["region"] = self.region_name
        if self.extra_regions:
            config_data["extra_regions"] = self.extra_regions
        if self.subnet_id:
            config_data["subnet"] = self.subnet_id
        return config_data

    @classmethod
    def deserialize(cls, config_data: Dict) -> Optional["AWSConfig"]:
        if config_data.get("backend") != "aws":
            return None
        try:
            bucket_name = config_data["bucket"]
        except KeyError:
            return None
        return cls(
            bucket_name=bucket_name,
            region_name=config_data.get("region"),
            extra_regions=config_data.get("extra_regions", []),
            subnet_id=config_data.get("subnet"),
        )
