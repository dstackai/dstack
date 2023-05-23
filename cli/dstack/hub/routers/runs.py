from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from dstack.backend.base import Backend
from dstack.core.job import JobStatus
from dstack.core.repo import RepoRef
from dstack.core.run import RunHead
from dstack.hub.models import RunsDelete, RunsList, RunsStop
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.permissions import ProjectMember
from dstack.hub.utils.common import run_async

router = APIRouter(prefix="/api/project", tags=["runs"], dependencies=[Depends(ProjectMember())])


@router.post(
    "/{project_name}/runs/create",
    response_model=str,
    response_class=PlainTextResponse,
)
async def create_run(project_name: str, repo_ref: RepoRef) -> str:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    run_name = await run_async(backend.create_run, repo_ref.repo_id)
    return run_name


@router.post(
    "/{project_name}/runs/list",
)
async def list_runs(project_name: str, body: RunsList) -> List[RunHead]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
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
    backend = get_backend(project)
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
    backend = get_backend(project)
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
