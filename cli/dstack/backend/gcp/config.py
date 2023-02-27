from pathlib import Path
from typing import Dict

import yaml

from dstack.core.config import BackendConfig, get_config_path


class GCPConfig(BackendConfig):
    @property
    def name(self):
        return "gcp"

    def __init__(
        self,
    ):
        self.credentials = None
        self.project_id = "dstack"
        self.zone = "us-central1-a"
        self.bucket_name = "dstack-bucket"

    def configure(self):
        pass

    @classmethod
    def load(cls, path: Path = get_config_path()):
        return cls()

    def save(self, path: Path = get_config_path()):
        pass

    def serialize(self) -> Dict:
        return {
            "backend": self.name,
            "project": self.project_id,
            "zone": self.zone,
            "bucket": self.bucket_name,
        }

    def serialize_yaml(self) -> str:
        return yaml.dump(self.serialize())
