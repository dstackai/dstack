from abc import ABC, abstractmethod
from enum import Enum
from typing import BinaryIO, Optional

from pydantic import BaseModel


class RepoType(str, Enum):
    REMOTE = "remote"
    LOCAL = "local"
    VIRTUAL = "virtual"


class RepoProtocol(str, Enum):
    SSH = "ssh"
    HTTPS = "https"


class BaseRepoInfo(BaseModel):
    repo_type: str


class Repo(ABC):
    repo_id: str
    repo_dir: Optional[str]
    run_repo_data: BaseRepoInfo

    @abstractmethod
    def write_code_file(self, fp: BinaryIO) -> str:
        pass
