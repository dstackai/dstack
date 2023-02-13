from pydantic import BaseModel

from dstack.core.repo import RepoAddress


class DepSpec(BaseModel):
    repo_address: RepoAddress
    run_name: str
    mount: bool

    def __str__(self) -> str:
        return (
            f"DepSpec(repo_address={self.repo_address}, "
            f'run_name="{self.run_name}",'
            f"mount={self.mount})"
        )
