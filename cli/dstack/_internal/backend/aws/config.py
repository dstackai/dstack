from typing import Dict, List, Optional

from pydantic import BaseModel

from dstack._internal.backend.base.config import BackendConfig

DEFAULT_REGION = "us-east-1"


class AWSConfig(BackendConfig, BaseModel):
    bucket_name: str
    regions: List[str]
    subnet_id: Optional[str] = None
    credentials: Optional[Dict] = None
    # dynamically set
    region: Optional[str] = DEFAULT_REGION

    def serialize(self) -> Dict:
        config_data = {
            "backend": "aws",
            "bucket": self.bucket_name,
            "regions": self.regions,
            "region": self.region,
        }
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
            regions=config_data.get("regions", []),
            subnet_id=config_data.get("subnet"),
            region=config_data.get("region"),
        )
