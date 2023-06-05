from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.artifact import ArtifactHead
from dstack._internal.utils.escape import escape_head


class TagHead(BaseModel):
    repo_id: str
    tag_name: str
    run_name: str
    workflow_name: Optional[str]
    provider_name: Optional[str]
    hub_user_name: str
    created_at: int
    artifact_heads: Optional[List[ArtifactHead]]

    def serialize_artifact_heads(self):
        return (
            ":".join([a.job_id + "=" + escape_head(a.artifact_path) for a in self.artifact_heads])
            if self.artifact_heads
            else ""
        )

    def key(self, add_prefix=True) -> str:
        prefix = ""
        if add_prefix:
            prefix = f"tags/{self.repo_id}/"
        key = (
            f"{prefix}l;{self.tag_name};"
            f"{self.run_name};"
            f"{self.workflow_name or ''};"
            f"{self.provider_name or ''};"
            f"{self.hub_user_name or ''};"
            f"{self.created_at};"
            f"{self.serialize_artifact_heads()}"
        )
        return key
