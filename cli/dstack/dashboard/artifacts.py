from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from dstack.backend import load_backend
from dstack.repo import RepoAddress

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


class ArtifactFileItem(BaseModel):
    name: str
    folder: bool


class BrowseArtifactsRequest(BaseModel):
    objects: List[ArtifactFileItem]


@router.get("/browse", response_model=BrowseArtifactsRequest)
async def query(repo_host_name: str, repo_port: Optional[int], repo_user_name: str, repo_name: str, job_id: str, path: str) -> BrowseArtifactsRequest:
    backend = load_backend()
    files_and_folders = backend.list_run_artifact_files_and_folders(
        RepoAddress(repo_host_name, repo_port, repo_user_name, repo_name), job_id, path)
    return BrowseArtifactsRequest(
        objects=[ArtifactFileItem(name=file_or_folder_name,
                                  folder=folder) for file_or_folder_name, folder in files_and_folders])
