from abc import ABC, abstractmethod
from typing import Optional


class BaseStorage(ABC):
    @abstractmethod
    def upload_code(
        self,
        project_id: str,
        repo_id: str,
        code_hash: str,
        blob: bytes,
    ):
        pass

    @abstractmethod
    def get_code(
        self,
        project_id: str,
        repo_id: str,
        code_hash: str,
    ) -> Optional[bytes]:
        pass

    @abstractmethod
    def upload_archive(
        self,
        user_id: str,
        archive_hash: str,
        blob: bytes,
    ):
        pass

    @abstractmethod
    def get_archive(
        self,
        user_id: str,
        archive_hash: str,
    ) -> Optional[bytes]:
        pass

    @staticmethod
    def _get_code_key(project_id: str, repo_id: str, code_hash: str) -> str:
        return f"data/projects/{project_id}/codes/{repo_id}/{code_hash}"

    @staticmethod
    def _get_archive_key(user_id: str, archive_hash: str) -> str:
        return f"data/users/{user_id}/file_archives/{archive_hash}"
