from pydantic.fields import Field
from typing_extensions import Annotated, List, Optional

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.repos.base import RepoType


class ProjectConfig(CoreModel):
    name: str
    url: str
    token: str
    default: Optional[bool]


# Not used since 0.20.0. Can be removed when most users update their `config.yml` (it's updated
# each time a project is added)
class RepoConfig(CoreModel):
    path: str
    repo_id: str
    repo_type: RepoType
    ssh_key_path: Annotated[Optional[str], Field(exclude=True)] = None


class GlobalConfig(CoreModel):
    projects: Annotated[List[ProjectConfig], Field(description="The list of projects")] = []
    repos: Annotated[list[RepoConfig], Field(exclude=True)] = []
    """`repos` is not used since 0.20.0. It can be removed when most users update their `config.yml`
    because it is updated each time a project is added.
    """
