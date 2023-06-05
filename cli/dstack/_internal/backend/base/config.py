import os
from abc import ABC, abstractmethod
from typing import Dict, Optional

import yaml

BACKEND_CONFIG_FILENAME = "backend.yaml"
RUNNER_CONFIG_FILENAME = "runner.yaml"
BACKEND_CONFIG_FILEPATH = os.path.expanduser(f"~/.dstack/{BACKEND_CONFIG_FILENAME}")


class BackendConfig(ABC):
    @abstractmethod
    def serialize(self) -> Dict:
        pass

    @classmethod
    @abstractmethod
    def deserialize(cls, config_data: Dict) -> Optional["BackendConfig"]:
        pass

    def serialize_yaml(self) -> str:
        return yaml.dump(self.serialize())

    @classmethod
    def deserialize_yaml(cls, yaml_content: str) -> Optional["BackendConfig"]:
        content = yaml.load(yaml_content, yaml.FullLoader)
        if content is None:
            return None
        return cls.deserialize(content)

    @classmethod
    def load(cls) -> Optional["BackendConfig"]:
        with open(BACKEND_CONFIG_FILEPATH) as f:
            return cls.deserialize_yaml(f.read())
