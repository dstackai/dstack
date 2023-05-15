from typing import Dict

from dstack.backend.base.config import BackendConfig
from dstack.utils.common import get_dstack_dir


class LocalConfig(BackendConfig):
    def __init__(self, namespace: str):
        self.namespace = namespace
        self.backend_dir = get_dstack_dir() / "local_backend" / self.namespace

    def serialize(self) -> Dict:
        return {
            "backend": "local",
            "namespace": self.namespace,
        }

    @classmethod
    def deserialize(cls, config_data: Dict) -> "LocalConfig":
        pass
