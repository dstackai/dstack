from typing import Dict, Optional

from dstack.core.config import BackendConfig
from dstack.core.error import ConfigError


class GCPConfig(BackendConfig):
    def __init__(
        self,
        project_id: str,
        region: str,
        zone: str,
        bucket_name: str,
        vpc: str,
        subnet: str,
        credentials_file: Optional[str] = None,
        credentials: Optional[Dict] = None,
    ):
        self.project_id = project_id
        self.region = region
        self.zone = zone
        self.bucket_name = bucket_name
        self.vpc = vpc
        self.subnet = subnet
        self.credentials_file = credentials_file
        self.credentials = credentials

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
            raise ConfigError(f"Not a GCP config")
        try:
            project_id = config_data["project"]
            region = config_data["region"]
            zone = config_data["zone"]
            bucket_name = config_data["bucket"]
            vpc = config_data["vpc"]
            subnet = config_data["subnet"]
        except KeyError:
            raise ConfigError("Cannot load config")

        return cls(
            project_id=project_id,
            region=region,
            zone=zone,
            bucket_name=bucket_name,
            vpc=vpc,
            subnet=subnet,
            credentials_file=config_data.get("credentials_file"),
            credentials=config_data.get("credentials"),
        )
