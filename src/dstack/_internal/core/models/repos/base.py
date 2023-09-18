from abc import ABC, abstractmethod
from enum import Enum
from typing import BinaryIO


class RepoType(str, Enum):
    REMOTE = "remote"
    LOCAL = "local"


class RepoProtocol(str, Enum):
    SSH = "ssh"
    HTTPS = "https"


class Repo(ABC):
    @abstractmethod
    def write_code_file(self, fp: BinaryIO) -> str:
        pass
