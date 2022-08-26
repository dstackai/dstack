from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from dstack.backend import load_backend

router = APIRouter(prefix="/api/artifacts")


class ArtifactObjectModel(BaseModel):
    object_name: str
    folder: bool


class ArtifactObjectListModel(BaseModel):
    objects: List[ArtifactObjectModel]


@router.get("/objects", response_model=ArtifactObjectListModel)
async def objects(repo_user_name: str, repo_name: str, job_id: str, path: str) -> ArtifactObjectListModel:
    backend = load_backend()
    objects = backend.list_run_artifact_objects(repo_user_name, repo_name, job_id, path)
    return ArtifactObjectListModel(
        objects=[ArtifactObjectModel(object_name=object_name,
                                     folder=folder) for object_name, folder in objects])
