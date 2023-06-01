from typing import Dict

from dstack._internal.backend.base.config import BackendConfig
from dstack._internal.utils.common import get_dstack_dir


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
        if config_data.get("backend") != "local":
            return None
        try:
            namespace = config_data["namespace"]
        except KeyError:
            return None
        return LocalConfig(namespace)
