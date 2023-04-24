from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, validator
from typing_extensions import Literal


class RepoProtocol(Enum):
    SSH = "ssh"
    HTTPS = "https"


# TODO: fix backend methods so that they don't require RepoRef or remove repo_user_id from RepoRef
class RepoRef(BaseModel):
    repo_type: Literal["remote"] = "remote"
    repo_id: str
    repo_user_id: str

    @validator("repo_id", "repo_user_id")
    def validate_id(cls, value):
        for c in "/;":
            if c in value:
                raise ValueError(f"id can't contain `{c}`")
        return value


class RepoData(BaseModel):
    repo_type: Literal["none"] = "none"


class RepoInfo(BaseModel):
    pass


class RepoHead(BaseModel):
    repo_type: Literal["none"] = "none"
    repo_id: str
    last_run_at: Optional[int] = None
    tags_count: int = 0
    repo_info: RepoInfo


class Repo(ABC):
    def __init__(self, repo_ref: RepoRef, repo_data: RepoData):
        self.repo_ref = repo_ref
        self.repo_data = repo_data

    @property
    def repo_id(self) -> str:
        return self.repo_ref.repo_id

    @property
    def repo_user_id(self) -> str:
        return self.repo_ref.repo_user_id

    @abstractmethod
    def get_workflows(self, credentials=None) -> Dict[str, Dict[str, Any]]:
        pass

    @abstractmethod
    def get_repo_diff(self) -> Optional[str]:
        pass
