from typing import List, Optional

from pydantic import BaseModel

from dstack.core.artifact import ArtifactHead
from dstack.core.repo import RepoAddress
from dstack.utils.common import _quoted


class TagHead(BaseModel):
    repo_address: RepoAddress
    tag_name: str
    run_name: str
    workflow_name: Optional[str]
    provider_name: Optional[str]
    local_repo_user_name: Optional[str]
    created_at: int
    artifact_heads: Optional[List[ArtifactHead]]

    def __str__(self) -> str:
        artifact_heads = (
            ("[" + ", ".join(map(lambda a: str(a), self.artifact_heads)) + "]")
            if self.artifact_heads
            else None
        )
        return (
            f"TagHead(repo_address={self.repo_address}, "
            f'tag_name="{self.tag_name}", '
            f'run_name="{self.run_name}", '
            f"workflow_name={_quoted(self.workflow_name)}, "
            f"provider_name={_quoted(self.provider_name)}, "
            f"local_repo_user_name={_quoted(self.local_repo_user_name)}, "
            f"created_at={self.created_at}, "
            f"artifact_heads={artifact_heads})"
        )

    def serialize_artifact_heads(self):
        return (
            ":".join(
                [a.job_id + "=" + a.artifact_path.replace("/", "_") for a in self.artifact_heads]
            )
            if self.artifact_heads
            else ""
        )

    def key(self, add_prefix=True) -> str:
        prefix = ""
        if add_prefix:
            prefix = f"tags/{self.repo_address.path()}/"
        key = (
            f"{prefix}l;{self.tag_name};"
            f"{self.run_name};"
            f"{self.workflow_name or ''};"
            f"{self.provider_name or ''};"
            f"{self.local_repo_user_name or ''};"
            f"{self.created_at};"
            f"{self.serialize_artifact_heads()}"
        )
        return key
