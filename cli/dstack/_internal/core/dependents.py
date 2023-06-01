from pydantic import BaseModel

from dstack._internal.core.repo import RepoRef


class DepSpec(BaseModel):
    repo_ref: RepoRef  # todo: remove
    run_name: str
    mount: bool
