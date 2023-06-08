from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.app import AppHead
from dstack._internal.core.artifact import ArtifactHead
from dstack._internal.core.job import JobHead, JobStatus
from dstack._internal.core.request import RequestHead, RequestStatus
from dstack._internal.utils import random_names


class RunHead(BaseModel):
    run_name: str
    workflow_name: Optional[str]
    provider_name: str
    configuration_path: Optional[str]
    hub_user_name: Optional[str]
    artifact_heads: Optional[List[ArtifactHead]]
    status: JobStatus
    submitted_at: int
    tag_name: Optional[str]
    app_heads: Optional[List[AppHead]]
    request_heads: Optional[List[RequestHead]]
    job_heads: List[JobHead]

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
