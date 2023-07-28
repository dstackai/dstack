from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from dstack._internal.backend.base import Backend
from dstack._internal.core.build import BuildNotFoundError
from dstack._internal.core.error import BackendValueError, NoMatchingInstanceError
from dstack._internal.core.job import JobStatus
from dstack._internal.core.plan import JobPlan, RunPlan
from dstack._internal.core.run import RunHead
from dstack._internal.hub.db.models import User
from dstack._internal.hub.models import (
    RunInfo,
    RunsCreate,
    RunsDelete,
    RunsGetPlan,
    RunsList,
    RunsStop,
)
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.routers.util import (
    call_backend,
    error_detail,
    get_backend,
    get_backend_if_available,
    get_project,
)
from dstack._internal.hub.security.permissions import Authenticated, ProjectMember
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


root_router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(Authenticated())])
project_router = APIRouter(
    prefix="/api/project", tags=["runs"], dependencies=[Depends(ProjectMember())]
)


@root_router.post("/list")
async def list_all_runs() -> List[RunInfo]:
    projects = await ProjectManager.list()
    run_infos = []
    for project in projects:
        backend = await get_backend_if_available(project)
        if backend is None:
            logger.warning(
                "Missing dependencies for %s backend. "
                "%s runs are not included in the response.",
                project.backend,
                project.name,
            )
            continue
        repo_heads = await call_backend(backend.list_repo_heads)
        for repo_head in repo_heads:
            run_heads = await call_backend(
                backend.list_run_heads,
                repo_head.repo_id,
                None,
                False,
                JobStatus.PENDING,
            )
            for run_head in run_heads:
                run_infos.append(RunInfo(project=project.name, repo=repo_head, run_head=run_head))
    return run_infos


@project_router.post("/{project_name}/runs/get_plan")
async def get_run_plan(
    project_name: str, body: RunsGetPlan, user: User = Depends(Authenticated())
) -> RunPlan:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    job_plans = []
    for job in body.jobs:
        instance_type = await call_backend(backend.predict_instance_type, job)
        if instance_type is None:
            msg = f"No instance type matching requirements ({job.requirements.pretty_format()})."
            if backend.name == "local":
                msg += " Ensure that enough CPU and memory are available for Docker containers or lower the requirements."
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(msg=msg, code=NoMatchingInstanceError.code),
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


@project_router.post(
    "/{project_name}/runs/create",
    response_model=str,
    response_class=PlainTextResponse,
)
async def create_run(project_name: str, body: RunsCreate) -> str:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    run_name = await call_backend(backend.create_run, body.repo_ref.repo_id, body.run_name)
    return run_name


@project_router.post(
    "/{project_name}/runs/list",
)
async def list_runs(project_name: str, body: RunsList) -> List[RunHead]:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    run_heads = await call_backend(
        backend.list_run_heads,
        body.repo_id,
        body.run_name,
        body.include_request_heads,
        JobStatus.PENDING,
    )
    return run_heads


@project_router.post(
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
            await call_backend(
                backend.stop_job,
                body.repo_id,
                job_head.job_id,
                False,
                body.abort,
            )


@project_router.post(
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
                    error_detail(f"Run {run_name} is not finished", code=BackendValueError.code)
                ],
            )
        run_heads.append(run_head)
    for run_head in run_heads:
        for job_head in run_head.job_heads:
            if job_head.status == JobStatus.STOPPED:
                # Force termination of a stopped run
                await call_backend(
                    backend.stop_job,
                    body.repo_id,
                    job_head.job_id,
                    True,
                    True,
                )
            await call_backend(
                backend.delete_job_head,
                body.repo_id,
                job_head.job_id,
            )
        await call_backend(backend.delete_run_jobs, body.repo_id, run_head.run_name)


async def _get_run_head(backend: Backend, repo_id: str, run_name: str) -> RunHead:
    run_head = await call_backend(
        backend.get_run_head,
        repo_id,
        run_name,
        False,
    )
    if run_head is not None:
        return run_head
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=[error_detail(f"Run {run_name} not found", code=BackendValueError.code)],
    )
