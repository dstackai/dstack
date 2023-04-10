from typing import Optional

from pydantic import BaseModel


class RepoUserConfig(BaseModel):
    ssh_key_path: Optional[str] = None
