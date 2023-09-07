from typing import List

from fastapi import APIRouter

from dstack._internal.core.runs import Run, RunPlan
from dstack._internal.server.schemas.runs import SubmitRunRequest

router = APIRouter(
    prefix="/api/project/{project_name}/runs",
    tags=["runs"],
)


@router.post("/list")
async def list_runs(project_name: str) -> List[Run]:
    pass


@router.post("/get")
async def get_run(project_name: str, body) -> Run:
    pass


@router.post("/get_plan")
async def get_run_plan(project_name: str, body: SubmitRunRequest) -> RunPlan:
    pass


@router.post("/submit")
async def submit_run(project_name: str, body: SubmitRunRequest):
    pass


@router.post("/stop")
async def stop_runs(project_name: str, body):
    pass


@router.post("/delete")
async def delete_runs(project_name: str, body):
    pass
