from typing import Dict

from dstack.core.config import BackendConfig, get_dstack_dir


class LocalConfig(BackendConfig):
    def __init__(self, namespace: str):
        self.dstack_dir = get_dstack_dir()
        self.namespace = namespace
        self.backend_dir = self.dstack_dir / "local_backend" / self.namespace

    def serialize(self) -> Dict:
        return {
            "backend": "local",
            "namespace": self.namespace,
        }

    @classmethod
    def deserialize(self, config_data: Dict) -> "LocalConfig":
        pass
