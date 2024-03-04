from typing import List, Optional

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.repos.base import RepoType


class ProjectConfig(CoreModel):
    name: str
    url: str
    token: str
    default: Optional[bool]


class RepoConfig(CoreModel):
    path: str
    repo_id: str
    repo_type: RepoType
    ssh_key_path: str


class GlobalConfig(CoreModel):
    projects: List[ProjectConfig] = []
    repos: List[RepoConfig] = []
