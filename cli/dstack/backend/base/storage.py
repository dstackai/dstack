from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional

from dstack.core.storage import StorageFile

SIGNED_URL_EXPIRATION = 3600


class Storage(ABC):
    @abstractmethod
    def put_object(self, key: str, content: str, metadata: Optional[Dict] = None):
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

    @abstractmethod
    def list_files(self, prefix: str, recursive: bool) -> List[StorageFile]:
        pass

    @abstractmethod
    def download_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        """
        `source_path` - storage path relative to the storage root.
        `dest_path` - local absolute path.
        """
        pass

    @abstractmethod
    def upload_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        """
        `source_path` - local absolute path.
        `dest_path` - storage path relative to the storage root.
        """
        pass

    def delete_prefix(self, keys_prefix: str):
        for key in self.list_objects(keys_prefix):
            self.delete_object(key)

    def key_exists(self, key: str) -> bool:
        return any(key == obj for obj in self.list_objects(key))


class CloudStorage(Storage):
    @abstractmethod
    def get_signed_download_url(self, key: str) -> str:
        pass

    @abstractmethod
    def get_signed_upload_url(self, key: str) -> str:
        pass
