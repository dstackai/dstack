from typing_extensions import Literal

from dstack.core.repo.base import RepoData, RepoRef


class LocalRepoData(RepoData):
    repo_type: Literal["local"] = "local"
