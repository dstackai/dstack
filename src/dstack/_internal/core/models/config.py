from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.repos.base import RepoType


class ProjectConfig(BaseModel):
    name: str
    url: str
    token: str
    default: Optional[bool]


class RepoConfig(BaseModel):
    path: str
    repo_id: str
    repo_type: RepoType
    ssh_key_path: str


class GlobalConfig(BaseModel):
    projects: List[ProjectConfig] = []
    repos: List[RepoConfig] = []
