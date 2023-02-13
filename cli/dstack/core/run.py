from typing import List, Optional

from pydantic import BaseModel

from dstack.core.app import AppHead
from dstack.core.artifact import ArtifactHead
from dstack.core.job import JobStatus
from dstack.core.repo import RepoAddress
from dstack.core.request import RequestHead, RequestStatus
from dstack.utils import random_names
from dstack.utils.common import _quoted


class RunHead(BaseModel):
    repo_address: RepoAddress
    run_name: str
    workflow_name: Optional[str]
    provider_name: str
    local_repo_user_name: Optional[str]
    artifact_heads: Optional[List[ArtifactHead]]
    status: JobStatus
    submitted_at: int
    tag_name: Optional[str]
    app_heads: Optional[List[AppHead]]
    request_heads: Optional[List[RequestHead]]

    def __str__(self) -> str:
        artifact_heads = (
            ("[" + ", ".join(map(lambda a: str(a), self.artifact_heads)) + "]")
            if self.artifact_heads
            else None
        )
        app_heads = (
            ("[" + ", ".join(map(lambda a: str(a), self.app_heads)) + "]")
            if self.app_heads
            else None
        )
        request_heads = (
            "[" + ", ".join(map(lambda e: _quoted(str(e)), self.request_heads)) + "]"
            if self.request_heads
            else None
        )
        return (
            f"Run(repo_address={self.repo_address}, "
            f'run_name="{self.run_name}", '
            f"workflow_name={_quoted(self.workflow_name)}, "
            f'provider_name="{self.provider_name}", '
            f"local_repo_user_name={_quoted(self.local_repo_user_name)}, "
            f"status=JobStatus.{self.status.name}, "
            f"submitted_at={self.submitted_at}, "
            f"artifact_heads={artifact_heads}, "
            f"tag_name={_quoted(self.tag_name)}, "
            f"app_heads={app_heads}, "
            f"request_heads={request_heads})"
        )

    def has_request_status(self, statuses: List[RequestStatus]):
        return self.status.is_unfinished() and any(
            filter(lambda s: s.status in statuses, self.request_heads or [])
        )


_adjectives = random_names.get_adjectives()
_adjectives_subset_1 = _adjectives[::2]
_adjectives_subset_2 = _adjectives[1::2]
_animals = random_names.get_animals()


def generate_local_run_name_prefix() -> str:
    return random_names.generate_name_from_sets(_adjectives_subset_1, _animals)


def generate_remote_run_name_prefix() -> str:
    return random_names.generate_name_from_sets(_adjectives_subset_2, _animals)
