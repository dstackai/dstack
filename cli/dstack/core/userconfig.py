from typing import Optional

from pydantic import BaseModel
from typing_extensions import Literal

from dstack.core.repo import RepoRef


class RepoUserConfig(BaseModel):
    repo_id: str
    repo_type: Literal["remote", "local"] = "remote"
    ssh_key_path: Optional[str] = None

    @property
    def repo_ref(self) -> RepoRef:
        return RepoRef(repo_id=self.repo_id)
