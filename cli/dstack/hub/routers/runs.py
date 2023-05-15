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

router = APIRouter(prefix="/api/project", tags=["runs"], dependencies=[Depends(ProjectMember())])


@router.post(
    "/{project_name}/runs/create",
    response_model=str,
    response_class=PlainTextResponse,
)
async def create_run(project_name: str, repo_ref: RepoRef) -> str:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    run_name = backend.create_run(repo_ref.repo_id)
    return run_name


@router.post(
    "/{project_name}/runs/list",
)
async def list_runs(project_name: str, body: RunsList) -> List[RunHead]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    run_heads = backend.list_run_heads(
        repo_id=body.repo_id,
        run_name=body.run_name,
        include_request_heads=body.include_request_heads,
        interrupted_job_new_status=JobStatus.PENDING,
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
        run_head = _get_run_head(backend, body.repo_id, run_name)
        run_heads.append(run_head)
    for run_head in run_heads:
        for job_head in run_head.job_heads:
            backend.stop_job(
                repo_id=body.repo_id,
                job_id=job_head.job_id,
                abort=body.abort,
            )


@router.post(
    "/{project_name}/runs/delete",
)
async def delete_runs(project_name: str, body: RunsDelete):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    run_heads: List[RunHead] = []
    for run_name in body.run_names:
        run_head = _get_run_head(backend, body.repo_id, run_name)
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
            backend.delete_job_head(
                repo_id=body.repo_id,
                job_id=job_head.job_id,
            )


def _get_run_head(backend: Backend, repo_id: str, run_name: str) -> RunHead:
    run_head = backend.get_run_head(
        repo_id=repo_id,
        run_name=run_name,
        include_request_heads=False,
    )
    if run_head is not None:
        return run_head
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=[error_detail(f"Run {run_name} not found", code="run_not_found")],
    )
