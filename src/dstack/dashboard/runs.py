from typing import Optional, List

from fastapi import APIRouter
from pydantic import BaseModel

from dstack.backend import load_backend

router = APIRouter(prefix="/api/runs", tags=["runs"])


class AppHeadItem(BaseModel):
    job_id: str
    app_name: str


class ArtifactHeadItem(BaseModel):
    job_id: str
    artifact_name: str


class RequestHeadItem(BaseModel):
    job_id: str
    status: str
    message: Optional[str]


class RunItem(BaseModel):
    repo_user_name: str
    repo_name: str
    run_name: str
    workflow_name: Optional[str]
    provider_name: str
    artifacts: Optional[List[ArtifactHeadItem]]
    status: str
    submitted_at: int
    tag_name: Optional[str]
    apps: Optional[List[AppHeadItem]]
    requests: Optional[List[RequestHeadItem]]


class QueryRunsResponse(BaseModel):
    runs: List[RunItem]


@router.get("/query", response_model=QueryRunsResponse)
async def query(repo_user_name: str, repo_name: str) -> QueryRunsResponse:
    backend = load_backend()
    runs = backend.list_runs(repo_user_name, repo_name, include_request_heads=True)
    return QueryRunsResponse(
        runs=[RunItem(
            repo_user_name=r.repo_user_name,
            repo_name=r.repo_name,
            run_name=r.run_name,
            workflow_name=r.workflow_name,
            provider_name=r.provider_name,
            artifacts=[ArtifactHeadItem(job_id=a.job_id, artifact_name=a.artifact_path)
                       for a in r.artifact_heads] if r.artifact_heads else None,
            status=r.status.value,
            submitted_at=r.submitted_at,
            tag_name=r.tag_name,
            apps=[AppHeadItem(job_id=a.job_id, app_name=a.app_name)
                  for a in r.app_heads] if r.app_heads else None,
            requests=[RequestHeadItem(job_id=r.job_id, status=r.status.value, message=r.message)
                      for r in r.request_heads] if r.request_heads else None) for r in runs])


class StopRunRequest(BaseModel):
    repo_user_name: str
    repo_name: str
    run_name: str
    abort: Optional[bool]


class DeleteRunRequest(BaseModel):
    repo_user_name: str
    repo_name: str
    run_name: str


@router.post("/stop")
async def stop(request: StopRunRequest):
    backend = load_backend()
    backend.stop_jobs(request.repo_user_name, request.repo_name, request.run_name, request.abort is True)


@router.post("/delete")
async def delete(request: DeleteRunRequest):
    backend = load_backend()
    backend.delete_job_heads(request.repo_user_name, request.repo_name, request.run_name)
