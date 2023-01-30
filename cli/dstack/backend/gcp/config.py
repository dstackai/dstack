from pathlib import Path

from dstack.core.config import BackendConfig, get_config_path


class GCPConfig(BackendConfig):
    def __init__(self):
        super().__init__()
        self.project_id = "dstack"
        self.zone = "us-central1-a"
        self.bucket_name = "dstack-bucket"

    def load(self, path: Path = get_config_path()):
        super().load(path=path)

    def save(self, path: Path = get_config_path()):
        pass
