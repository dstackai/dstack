from pathlib import Path
from typing import Dict

from dstack.core.config import BackendConfig, get_config_path


class GCPConfig(BackendConfig):
    @property
    def name(self):
        return "gcp"

    def __init__(
        self,
    ):
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
            "project_id": self.project_id,
            "zone": self.zone,
            "bucket": self.bucket_name,
        }
