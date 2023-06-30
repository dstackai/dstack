from typing import Dict

from pydantic import BaseModel, ValidationError
from typing_extensions import Literal

from dstack._internal.backend.base.config import BackendConfig
from dstack._internal.utils.common import get_dstack_dir


class LocalConfig(BackendConfig, BaseModel):
    backend: Literal["local"] = "local"
    namespace: str

    def serialize(self) -> Dict:
        return self.dict()

    @classmethod
    def deserialize(cls, config_data: Dict) -> "LocalConfig":
        if config_data.get("backend") != "local":
            return None
        try:
            return cls.parse_obj(config_data)
        except ValidationError:
            return None

    @property
    def backend_dir(self):
        return get_dstack_dir() / "local_backend" / self.namespace
