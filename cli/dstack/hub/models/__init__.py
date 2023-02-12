from pydantic import BaseModel
from typing import Optional, List, Dict, Union

from dstack.core.repo import RepoAddress, LocalRepoData
from dstack.core.job import Job


class Hub(BaseModel):
    name: str
    backend: str
    config: str


class HubInfo(BaseModel):
    name: str
    backend: str


class UserInfo(BaseModel):
    user_name: str


class AddTagRun(BaseModel):
    repo_address: RepoAddress
    tag_name: str
    run_name: str
    run_jobs: List[Job]


class AddTagPath(BaseModel):
    repo_data: LocalRepoData
    tag_name: str
    local_dirs: List[str]
