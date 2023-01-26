from typing import Optional, List

from dstack.core.artifact import ArtifactHead
from dstack.core.repo import RepoAddress
from dstack.util import _quoted
class TagHead:
    def __init__(self, repo_address: RepoAddress, tag_name: str, run_name: str, workflow_name: Optional[str],
                 provider_name: Optional[str], local_repo_user_name: Optional[str], created_at: int,
                 artifact_heads: Optional[List[ArtifactHead]]):
        self.repo_address = repo_address
        self.tag_name = tag_name
        self.run_name = run_name
        self.workflow_name = workflow_name
        self.provider_name = provider_name
        self.local_repo_user_name = local_repo_user_name
        self.created_at = created_at
        self.artifact_heads = artifact_heads

    def __str__(self) -> str:
        artifact_heads = (
                "[" + ", ".join(map(lambda a: str(a), self.artifact_heads)) + "]") if self.artifact_heads else None
        return f'TagHead(repo_address={self.repo_address}, ' \
               f'tag_name="{self.tag_name}", ' \
               f'run_name="{self.run_name}", ' \
               f'workflow_name={_quoted(self.workflow_name)}, ' \
               f'provider_name={_quoted(self.provider_name)}, ' \
               f'local_repo_user_name={_quoted(self.local_repo_user_name)}, ' \
               f'created_at={self.created_at}, ' \
               f'artifact_heads={artifact_heads})'

