from typing import List, Optional

from dstack.core.artifact import ArtifactHead, ArtifactSpec
from dstack.core.job import Job, JobStatus
from dstack.core.repo import RepoAddress, RepoData
from dstack.core.tag import TagHead


def create_tag_from_local_dirs(
    path: str, repo_data: RepoData, tag_name: str, local_dirs: List[str]
):
    pass
