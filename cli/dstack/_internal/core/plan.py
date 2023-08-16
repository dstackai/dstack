from typing import List

from pydantic import BaseModel

from dstack._internal.core.instance import InstanceCandidate
from dstack._internal.core.job import Job


class JobPlan(BaseModel):
    job: Job
    candidates: List[InstanceCandidate]


class RunPlan(BaseModel):
    project: str
    hub_user_name: str
    job_plans: List[JobPlan]
    local_backend: bool = False  # deprecated
