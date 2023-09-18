from pydantic import BaseModel

from dstack._internal.core.models.runs import RunSpec


class GetRunRequest(BaseModel):
    run_name: str


class GetRunPlanRequest(BaseModel):
    run_spec: RunSpec


class SubmitRunRequest(BaseModel):
    run_spec: RunSpec
