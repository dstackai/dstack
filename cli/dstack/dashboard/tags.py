from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dstack.backend import load_backend

router = APIRouter(prefix="/api/tags", tags=["tags"])


class ArtifactHeadItem(BaseModel):
    job_id: str
    artifact_path: str


class TagHeadItem(BaseModel):
    repo_user_name: str
    repo_name: str
    tag_name: str
    run_name: str
    workflow_name: Optional[str]
    provider_name: Optional[str]
    created_at: int
    artifacts: Optional[List[ArtifactHeadItem]]


class TagItem(BaseModel):
    repo_user_name: str
    repo_name: str
    repo_branch: str
    repo_hash: str
    repo_diff: str
    tag_name: str
    run_name: str
    workflow_name: Optional[str]
    provider_name: Optional[str]
    created_at: int
    artifacts: Optional[List[ArtifactHeadItem]]


class QueryTagsResponse(BaseModel):
    tags: List[TagHeadItem]


class DeleteTagRequest(BaseModel):
    repo_user_name: str
    repo_name: str
    tag_name: str


class AddTagRequest(BaseModel):
    repo_user_name: str
    repo_name: str
    run_name: str
    tag_name: str


class GetTagResponse(BaseModel):
    tag: TagItem


@router.get("/query", response_model=QueryTagsResponse)
async def query(repo_user_name: str, repo_name: str) -> QueryTagsResponse:
    backend = load_backend()
    tag_heads = backend.list_tag_heads(repo_user_name, repo_name)
    return QueryTagsResponse(
        tags=[TagHeadItem(repo_user_name=t.repo_user_name,
                          repo_name=t.repo_name,
                          tag_name=t.tag_name,
                          run_name=t.run_name,
                          workflow_name=t.workflow_name,
                          provider_name=t.provider_name,
                          created_at=t.created_at,
                          artifacts=[
                              ArtifactHeadItem(job_id=a.job_id, artifact_path=a.artifact_path)
                              for a in t.artifact_heads
                          ] if t.artifact_heads else None) for t in tag_heads])


@router.get("/get", response_model=GetTagResponse)
async def query(repo_user_name: str, repo_name: str, tag_name: str) -> GetTagResponse:
    backend = load_backend()
    t = backend.get_tag_head(repo_user_name, repo_name, tag_name)
    if t:
        j = backend.list_jobs(repo_user_name, repo_name, t.run_name)[0]
        return GetTagResponse(
            tag=TagItem(repo_user_name=t.repo_user_name,
                        repo_name=t.repo_name,
                        repo_branch=j.repo_data.repo_branch,
                        repo_hash=j.repo_data.repo_hash,
                        repo_diff=j.repo_data.repo_diff,
                        tag_name=t.tag_name,
                        run_name=t.run_name,
                        workflow_name=t.workflow_name,
                        provider_name=t.provider_name,
                        created_at=t.created_at,
                        artifacts=[
                            ArtifactHeadItem(job_id=a.job_id, artifact_path=a.artifact_path)
                            for a in t.artifact_heads
                        ] if t.artifact_heads else None))
    else:
        raise HTTPException(status_code=404, detail="Tag not found")


@router.post("/delete")
async def delete(request: DeleteTagRequest):
    backend = load_backend()
    tag_head = backend.get_tag_head(request.repo_user_name, request.repo_name, request.tag_name)
    if tag_head:
        backend.delete_tag_head(request.repo_user_name, request.repo_name, tag_head)
    else:
        raise HTTPException(status_code=404, detail="Tag not found")


@router.post("/add")
async def delete(request: AddTagRequest):
    backend = load_backend()
    backend.add_tag_from_run(request.repo_user_name, request.repo_name, request.tag_name, request.run_name,
                             run_jobs=None)
