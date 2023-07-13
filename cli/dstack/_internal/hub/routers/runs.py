from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from dstack._internal.backend.base import Backend
from dstack._internal.core.build import BuildNotFoundError
from dstack._internal.core.error import NoMatchingInstanceError
from dstack._internal.core.job import Job, JobStatus
from dstack._internal.core.plan import JobPlan, RunPlan
from dstack._internal.core.repo import RepoRef
from dstack._internal.core.run import RunHead
from dstack._internal.hub.db.models import User
from dstack._internal.hub.models import RunsDelete, RunsGetPlan, RunsList, RunsStop
from dstack._internal.hub.routers.util import error_detail, get_backend, get_project
from dstack._internal.hub.security.permissions import Authenticated, ProjectMember
from dstack._internal.hub.utils.common import run_async

router = APIRouter(prefix="/api/project", tags=["runs"], dependencies=[Depends(ProjectMember())])


@router.post("/{project_name}/runs/get_plan")
async def get_run_plan(
    project_name: str, body: RunsGetPlan, user: User = Depends(Authenticated())
) -> RunPlan:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    job_plans = []
    for job in body.jobs:
        instance_type = await run_async(backend.predict_instance_type, job)
        if instance_type is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(
                    msg=NoMatchingInstanceError.message, code=NoMatchingInstanceError.code
                ),
            )
        try:
            build = backend.predict_build_plan(job)
        except BuildNotFoundError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(msg=e.message, code=e.code),
            )
        job_plans.append(JobPlan(job=job, instance_type=instance_type, build_plan=build))
    run_plan = RunPlan(project=project_name, hub_user_name=user.name, job_plans=job_plans)
    return run_plan


@router.post(
    "/{project_name}/runs/create",
    response_model=str,
    response_class=PlainTextResponse,
)
async def create_run(project_name: str, repo_ref: RepoRef) -> str:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    run_name = await run_async(backend.create_run, repo_ref.repo_id)
    return run_name


@router.post(
    "/{project_name}/runs/list",
)
async def list_runs(project_name: str, body: RunsList) -> List[RunHead]:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    run_heads = await run_async(
        backend.list_run_heads,
        body.repo_id,
        body.run_name,
        body.include_request_heads,
        JobStatus.PENDING,
    )
    return run_heads


@router.post(
    "/{project_name}/runs/stop",
)
async def stop_runs(project_name: str, body: RunsStop):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    run_heads: List[RunHead] = []
    for run_name in body.run_names:
        run_head = await _get_run_head(backend, body.repo_id, run_name)
        run_heads.append(run_head)
    for run_head in run_heads:
        for job_head in run_head.job_heads:
            await run_async(
                backend.stop_job,
                body.repo_id,
                job_head.job_id,
                body.abort,
            )


@router.post(
    "/{project_name}/runs/delete",
)
async def delete_runs(project_name: str, body: RunsDelete):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    run_heads: List[RunHead] = []
    for run_name in body.run_names:
        run_head = await _get_run_head(backend, body.repo_id, run_name)
        if run_head.status.is_unfinished():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=[
                    error_detail(
                        f"Run {run_name} is not finished", code="cannot_delete_unfinished_run"
                    )
                ],
            )
        run_heads.append(run_head)
    for run_head in run_heads:
        for job_head in run_head.job_heads:
            await run_async(
                backend.delete_job_head,
                body.repo_id,
                job_head.job_id,
            )


async def _get_run_head(backend: Backend, repo_id: str, run_name: str) -> RunHead:
    run_head = await run_async(
        backend.get_run_head,
        repo_id,
        run_name,
        False,
    )
    if run_head is not None:
        return run_head
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=[error_detail(f"Run {run_name} not found", code="run_not_found")],
    )
