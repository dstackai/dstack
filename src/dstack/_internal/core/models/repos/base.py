from abc import ABC, abstractmethod
from enum import Enum
from typing import BinaryIO, Optional

import dstack._internal.core.models.repos as repos
from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.common import CoreModel


class RepoType(str, Enum):
    REMOTE = "remote"
    LOCAL = "local"
    VIRTUAL = "virtual"


class BaseRepoInfo(CoreModel):
    repo_type: str


class Repo(ABC):
    repo_id: str
    repo_dir: Optional[str]
    run_repo_data: "repos.AnyRunRepoData"

    @abstractmethod
    def write_code_file(self, fp: BinaryIO) -> str:
        pass

    @abstractmethod
    def get_repo_info(self) -> "repos.AnyRepoInfo":
        pass

    def get_repo_dir_or_error(self) -> str:
        if self.repo_dir is not None:
            return self.repo_dir
        raise DstackError("repo_dir is None")
