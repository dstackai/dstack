from pydantic.fields import Field
from typing_extensions import Annotated, List, Optional

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
    # Deprecated since 0.19.25, not used. Can be removed when most users update their `config.yml`
    # (it's updated each time a project or repo is added)
    ssh_key_path: Annotated[Optional[str], Field(exclude=True)] = None


class GlobalConfig(CoreModel):
    projects: Annotated[List[ProjectConfig], Field(description="The list of projects")] = []
    repos: List[RepoConfig] = []
