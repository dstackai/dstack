from abc import ABC, abstractmethod
from enum import Enum
from typing import BinaryIO

from pydantic import BaseModel


class RepoType(str, Enum):
    REMOTE = "remote"
    LOCAL = "local"


class RepoProtocol(str, Enum):
    SSH = "ssh"
    HTTPS = "https"


class Repo(ABC):
    repo_id: str
    run_repo_data: BaseModel  # TODO make it more specific

    @abstractmethod
    def write_code_file(self, fp: BinaryIO) -> str:
        pass
