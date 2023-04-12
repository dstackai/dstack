from typing import Optional

from pydantic import BaseModel


class RepoUserConfig(BaseModel):
    repo_id: str
    repo_user_id: str = "default"
    ssh_key_path: Optional[str] = None
