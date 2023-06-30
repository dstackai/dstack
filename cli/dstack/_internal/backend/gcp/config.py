from typing import Dict, Optional

from pydantic import BaseModel, ValidationError
from typing_extensions import Literal

from dstack._internal.backend.base.config import BackendConfig


class GCPConfig(BackendConfig, BaseModel):
    backend: Literal["gcp"] = "gcp"
    project_id: str
    region: str
    zone: str
    bucket_name: str
    vpc: str
    subnet: str
    credentials_file: Optional[str] = None
    credentials: Optional[Dict] = None

    def serialize(self) -> Dict:
        res = {
            "backend": "gcp",
            "project": self.project_id,
            "region": self.region,
            "zone": self.zone,
            "bucket": self.bucket_name,
            "vpc": self.vpc,
            "subnet": self.subnet,
        }
        if self.credentials_file is not None:
            res["credentials_file"] = self.credentials_file
        return res

    @classmethod
    def deserialize(cls, config_data: Dict) -> Optional["GCPConfig"]:
        if config_data.get("backend") != "gcp":
            return None
        try:
            return cls.parse_obj(
                {
                    **config_data,
                    "project_id": config_data["project"],
                    "bucket_name": config_data["bucket"],
                }
            )
        except ValidationError:
            return None
