import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from dstack._internal.backend.base import Backend
from dstack._internal.core.error import BackendValueError, NoMatchingInstanceError
from dstack._internal.core.instance import InstanceAvailability, InstanceCandidate
from dstack._internal.core.job import JobStatus
from dstack._internal.core.plan import JobPlan, RunPlan
from dstack._internal.core.repo.head import RepoHead
from dstack._internal.core.run import generate_remote_run_name_prefix
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.db.models import Project, User
from dstack._internal.hub.repository.jobs import JobManager
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.routers.util import call_backend, error_detail, get_project
from dstack._internal.hub.schemas import (
    RunInfo,
    RunsCreate,
    RunsDelete,
    RunsGetPlan,
    RunsList,
    RunsStop,
)
from dstack._internal.hub.security.permissions import Authenticated, ProjectMember
from dstack._internal.hub.services.common import get_backends, get_instance_candidates
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


root_router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(Authenticated())])
project_router = APIRouter(
    prefix="/api/project", tags=["runs"], dependencies=[Depends(ProjectMember())]
)


@root_router.post("/list")
async def list_all_runs() -> List[RunInfo]:
    async def get_run_infos(
        project: Project, db_backend: DBBackend, backend: Backend, repo_head: RepoHead
    ) -> List[RunInfo]:
        run_infos = []
        run_heads = await call_backend(
            backend.list_run_heads,
            repo_head.repo_id,
            None,
            False,
        )
        for run_head in run_heads:
            run_info = RunInfo(
                project=project.name,
                repo_id=repo_head.repo_id,
                backend=db_backend.name,
                run_head=run_head,
                repo=repo_head,
            )
            run_infos.append(run_info)
        return run_infos

    projects = await ProjectManager.list()
    coros = []
    for project in projects:
        backends = await get_backends(project)
        for db_backend, backend in backends:
            repo_heads = await call_backend(backend.list_repo_heads)
            for repo_head in repo_heads:
                coros.append(get_run_infos(project, db_backend, backend, repo_head))
    res = await asyncio.gather(*coros)
    run_infos = [run_info for l in res for run_info in l]
    for project in projects:
        run_infos += await _get_not_started_run_infos(project)
    run_infos = sorted(run_infos, key=lambda x: -x.run_head.submitted_at)
    return run_infos


@project_router.post("/{project_name}/runs/get_plan")
async def get_run_plan(
    project_name: str, body: RunsGetPlan, user: User = Depends(Authenticated())
) -> RunPlan:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project, selected_backends=body.jobs[0].backends)
    backends = [backend for _, backend in backends]

    job_candidates = [(job, get_instance_candidates(backends, job)) for job in body.jobs]
    job_plans = []
    for job, candidates in job_candidates:
        candidates = await candidates
        if not candidates:
            msg = f"No available instance type matching requirements ({job.requirements.pretty_format()})"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(msg=msg, code=NoMatchingInstanceError.code),
            )

        job_plan = JobPlan(
            job=job,
            candidates=[
                InstanceCandidate(**offer.dict(), backend=backend.name)
                for backend, offer in candidates[:50]
            ],
        )
        job_plans.append(job_plan)
    run_plan = RunPlan(
        project=project_name,
        hub_user_name=user.name,
        job_plans=job_plans,
    )
    return run_plan


@project_router.post(
    "/{project_name}/runs/create",
    response_model=str,
    response_class=PlainTextResponse,
)
async def create_run(project_name: str, body: RunsCreate) -> str:
    project = await get_project(project_name=project_name)
    run_name = await _create_run(project=project, repo_id=body.repo_id, run_name=body.run_name)
    return run_name


@project_router.post(
    "/{project_name}/runs/list",
)
async def list_runs(project_name: str, body: RunsList) -> List[RunInfo]:
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    run_infos = []
    for db_backend, backend in backends:
        run_heads = await call_backend(
            backend.list_run_heads,
            body.repo_id,
            body.run_name,
            body.include_request_heads,
        )
        for run_head in run_heads:
            run_info = RunInfo(
                project=project.name,
                repo_id=body.repo_id,
                backend=db_backend.name,
                run_head=run_head,
            )
            run_infos.append(run_info)
    run_infos += await _get_not_started_run_infos(project)
    run_infos = sorted(run_infos, key=lambda x: -x.run_head.submitted_at)
    return run_infos


@project_router.post(
    "/{project_name}/runs/stop",
)
async def stop_runs(project_name: str, body: RunsStop):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for run_name in body.run_names:
        await JobManager.stop_jobs(project_name=project_name, run_name=run_name)
        for _, backend in backends:
            run_head = await call_backend(
                backend.get_run_head,
                body.repo_id,
                run_name,
                False,
            )
            if run_head is not None:
                for job_head in run_head.job_heads:
                    await call_backend(
                        backend.stop_job,
                        body.repo_id,
                        job_head.job_id,
                        body.terminate,
                        body.abort,
                    )
                break


@project_router.post(
    "/{project_name}/runs/delete",
)
async def delete_runs(project_name: str, body: RunsDelete):
    project = await get_project(project_name=project_name)
    backends = await get_backends(project)
    for run_name in body.run_names:
        await JobManager.delete_run_jobs(project_name=project_name, run_name=run_name)
        for _, backend in backends:
            run_head = await call_backend(
                backend.get_run_head,
                body.repo_id,
                run_name,
                False,
            )
            if run_head is not None:
                if run_head.status.is_unfinished():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[
                            error_detail(
                                f"Run {run_name} is not finished", code=BackendValueError.code
                            )
                        ],
                    )
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
                break


async def _create_run(project: Project, repo_id: str, run_name: Optional[str]) -> str:
    backends = await get_backends(project)
    job_heads = []
    for _, backend in backends:
        job_heads += await call_backend(backend.list_job_heads, repo_id)
    run_names = {job_head.run_name for job_head in job_heads}
    if run_name is not None:
        if run_name in run_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=[error_detail(f"Run {run_name} exists", code=BackendValueError.code)],
            )
        return run_name
    run_name_prefix = generate_remote_run_name_prefix()
    i = 1
    while True:
        run_name = f"{run_name_prefix}-{i}"
        if run_name not in run_names:
            return run_name
        i += 1


async def _get_not_started_run_infos(project: Project) -> List[RunInfo]:
    run_infos = []
    pending_runs = await JobManager.list_runs(project_name=project.name)
    for run_head in pending_runs:
        run_info = RunInfo(
            project=project.name,
            repo_id=run_head.job_heads[0].repo_ref.repo_id,
            backend=None,
            run_head=run_head,
        )
        run_infos.append(run_info)
    return run_infos
