from typing import List

from pydantic import BaseModel

from dstack.core.storage import StorageFile


class ArtifactSpec(BaseModel):
    artifact_path: str
    mount: bool = False

    def __str__(self) -> str:
        return f'ArtifactSpec(artifact_path="{self.artifact_path}", ' f"mount={self.mount})"


class ArtifactHead(BaseModel):
    job_id: str
    artifact_path: str

    def __str__(self) -> str:
        return f'ArtifactHead(job_id="{self.job_id}", artifact_path="{self.artifact_path})'


class Artifact(BaseModel):
    job_id: str
    name: str
    path: str
    files: List[StorageFile]
