from dstack.core.repo import RepoAddress


class DepSpec:
    def __init__(self, repo_address: RepoAddress, run_name: str, mount: bool):
        self.repo_address = repo_address
        self.run_name = run_name
        self.mount = mount

    def __str__(self) -> str:
        return (
            f"DepSpec(repo_address={self.repo_address}, "
            f'run_name="{self.run_name}",'
            f"mount={self.mount})"
        )
