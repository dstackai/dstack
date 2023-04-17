from pydantic import BaseModel

from dstack.core.repo import RepoRef


class DepSpec(BaseModel):
    repo_ref: RepoRef
    run_name: str
    mount: bool
