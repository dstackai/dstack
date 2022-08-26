from typing import Optional, List

from fastapi import APIRouter
from pydantic import BaseModel

from dstack.backend import load_backend

router = APIRouter(prefix="/api/runs")


class AppModel(BaseModel):
    job_id: str
    app_name: str


class ArtifactModel(BaseModel):
    job_id: str
    artifact_name: str


class RequestModel(BaseModel):
    job_id: str
    status: str
    message: Optional[str]


class RunModel(BaseModel):
    repo_user_name: str
    repo_name: str
    run_name: str
    workflow_name: Optional[str]
    provider_name: str
    artifacts: Optional[List[ArtifactModel]]
    status: str
    submitted_at: int
    tag_name: Optional[str]
    apps: Optional[List[AppModel]]
    requests: Optional[List[RequestModel]]


class RunListModel(BaseModel):
    runs: List[RunModel]


@router.get("/query", response_model=RunListModel)
async def query(repo_user_name: str, repo_name: str) -> RunListModel:
    backend = load_backend()
    runs = backend.list_runs(repo_user_name, repo_name, include_request_heads=True)
    return RunListModel(
        runs=[RunModel(
            repo_user_name=r.repo_user_name,
            repo_name=r.repo_name,
            run_name=r.run_name,
            workflow_name=r.workflow_name,
            provider_name=r.provider_name,
            artifacts=[ArtifactModel(job_id=a.job_id, artifact_name=a.artifact_name)
                       for a in r.artifact_heads] if r.artifact_heads else None,
            status=r.status.value,
            submitted_at=r.submitted_at,
            tag_name=r.tag_name,
            apps=[RequestModel(jop_id=a.job_id, app_name=a.app_name)
                  for a in r.app_heads] if r.app_heads else None,
            requests=[RequestModel(jop_id=r.job_id, status=r.status.value)
                      for r in r.request_heads] if r.request_heads else None) for r in runs])
