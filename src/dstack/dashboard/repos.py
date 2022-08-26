from typing import Optional, List

from fastapi import APIRouter
from pydantic import BaseModel

from dstack.backend import load_backend

router = APIRouter(prefix="/api/repos")


class RepoModel(BaseModel):
    repo_user_name: str
    repo_name: str
    last_run_at: Optional[int]
    tags_count: int


class RepoListModel(BaseModel):
    repos: List[RepoModel]


@router.get("/query", response_model=RepoListModel)
async def query() -> RepoListModel:
    backend = load_backend()
    repo_heads = backend.list_repo_heads()
    return RepoListModel(
        repos=[RepoModel(repo_user_name=r.repo_user_name,
                         repo_name=r.repo_name,
                         last_run_at=r.last_run_at,
                         tags_count=r.tags_count) for r in repo_heads])
