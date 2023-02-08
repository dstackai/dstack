from abc import ABC, abstractmethod
from typing import List, Optional


class Storage(ABC):
    @abstractmethod
    def put_object(self, key: str, content: str):
        pass

    @abstractmethod
    def get_object(self, key: str) -> Optional[str]:
        pass

    @abstractmethod
    def delete_object(self, key: str):
        pass

    @abstractmethod
    def list_objects(self, keys_prefix: str) -> List[str]:
        pass
