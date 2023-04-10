from typing import Optional

from pydantic import BaseModel


class RepoUserConfig(BaseModel):
    repo_name: str
    username: str = "default"
    ssh_key_path: Optional[str] = None
