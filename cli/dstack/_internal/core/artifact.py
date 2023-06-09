from typing import List

from pydantic import BaseModel

from dstack._internal.core.storage import StorageFile


class ArtifactSpec(BaseModel):
    artifact_path: str
    mount: bool = False


class ArtifactHead(BaseModel):
    job_id: str
    artifact_path: str


class Artifact(BaseModel):
    job_id: str
    name: str
    path: str
    files: List[StorageFile]
