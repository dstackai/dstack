from abc import ABC, abstractmethod
from typing import Dict, Optional

import yaml


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
