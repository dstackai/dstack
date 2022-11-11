from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dstack.backend import load_backend
from dstack.repo import RepoAddress

router = APIRouter(prefix="/api/runs", tags=["runs"])


class AppHeadItem(BaseModel):
    job_id: str
    app_name: str


class ArtifactHeadItem(BaseModel):
    job_id: str
    artifact_path: str


class RequestHeadItem(BaseModel):
    job_id: str
    status: str
    message: Optional[str]


class RunHeadItem(BaseModel):
    repo_host_name: str
    repo_port: Optional[int]
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


class RunItem(BaseModel):
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str
    repo_branch: str
    repo_hash: str
    repo_diff: Optional[str]
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
    runs: List[RunHeadItem]


class GetRunResponse(BaseModel):
    run: RunItem


@router.get("/query", response_model=QueryRunsResponse)
async def query(repo_host_name: str, repo_port: Optional[int], repo_user_name: str, repo_name: str) -> QueryRunsResponse:
    backend = load_backend()
    runs = backend.list_run_heads(RepoAddress(repo_host_name, repo_port, repo_user_name, repo_name),
                                  include_request_heads=True)
    return QueryRunsResponse(
        runs=[RunHeadItem(
            repo_host_name = r.repo_address.repo_host_name,
            repo_port = r.repo_address.repo_port,
            repo_user_name=r.repo_address.repo_user_name,
            repo_name=r.repo_address.repo_name,
            run_name=r.run_name,
            workflow_name=r.workflow_name,
            provider_name=r.provider_name,
            artifacts=[ArtifactHeadItem(job_id=a.job_id, artifact_path=a.artifact_path)
                       for a in r.artifact_heads] if r.artifact_heads else None,
            status=r.status.value,
            submitted_at=r.submitted_at,
            tag_name=r.tag_name,
            apps=[AppHeadItem(job_id=a.job_id, app_name=a.app_name)
                  for a in r.app_heads] if r.app_heads else None,
            requests=[RequestHeadItem(job_id=r.job_id, status=r.status.value, message=r.message)
                      for r in r.request_heads] if r.request_heads else None) for r in runs])


@router.get("/get", response_model=GetRunResponse)
async def get(repo_host_name: str, repo_port: Optional[int], repo_user_name: str, repo_name: str, run_name: str) -> GetRunResponse:
    backend = load_backend()
    repo_address = RepoAddress(repo_host_name, repo_port, repo_user_name, repo_name)
    job_heads = backend.list_job_heads(repo_address, run_name)
    if job_heads:
        r = backend.get_run_heads(repo_address, job_heads)[0]
        j = backend.get_job(repo_address, job_heads[0].job_id)
        return GetRunResponse(
            run=RunItem(
                repo_host_name=r.repo_address.repo_host_name,
                repo_port=r.repo_address.repo_port,
                repo_user_name=r.repo_address.repo_user_name,
                repo_name=r.repo_address.repo_name,
                repo_branch=j.repo_data.repo_branch,
                repo_hash=j.repo_data.repo_hash,
                repo_diff=j.repo_data.repo_diff,
                run_name=r.run_name,
                workflow_name=r.workflow_name,
                provider_name=r.provider_name,
                artifacts=[ArtifactHeadItem(job_id=a.job_id, artifact_path=a.artifact_path)
                           for a in r.artifact_heads] if r.artifact_heads else None,
                status=r.status.value,
                submitted_at=r.submitted_at,
                tag_name=r.tag_name,
                apps=[AppHeadItem(job_id=a.job_id, app_name=a.app_name)
                      for a in r.app_heads] if r.app_heads else None,
                requests=[RequestHeadItem(job_id=r.job_id, status=r.status.value, message=r.message)
                          for r in r.request_heads] if r.request_heads else None))
    else:
        raise HTTPException(status_code=404, detail="Run not found")


class StopRunRequest(BaseModel):
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str
    run_name: str
    abort: Optional[bool]


class DeleteRunRequest(BaseModel):
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str
    run_name: str


@router.post("/stop")
async def stop(request: StopRunRequest):
    backend = load_backend()
    backend.stop_jobs(RepoAddress(request.repo_host_name, request.repo_port, request.repo_user_name, request.repo_name),
                      request.run_name, request.abort is True)


@router.post("/delete")
async def delete(request: DeleteRunRequest):
    backend = load_backend()
    backend.delete_job_heads(
        RepoAddress(request.repo_host_name, request.repo_port, request.repo_user_name, request.repo_name),
        request.run_name)
