from typing import Optional, List

from dstack.util import _quoted
from dstack.core.app import AppHead
from dstack.core.artifact import ArtifactHead
from dstack.core.repo import RepoAddress
from dstack.core.request import RequestHead
from dstack.core.job import JobStatus


class RunHead:
    def __init__(self, repo_address: RepoAddress, run_name: str, workflow_name: Optional[str], provider_name: str,
                 local_repo_user_name: Optional[str], artifact_heads: Optional[List[ArtifactHead]], status: JobStatus,
                 submitted_at: int, tag_name: Optional[str], app_heads: Optional[List[AppHead]],
                 request_heads: Optional[List[RequestHead]]):
        self.repo_address = repo_address
        self.run_name = run_name
        self.workflow_name = workflow_name
        self.provider_name = provider_name
        self.local_repo_user_name = local_repo_user_name
        self.artifact_heads = artifact_heads
        self.status = status
        self.submitted_at = submitted_at
        self.tag_name = tag_name
        self.app_heads = app_heads
        self.request_heads = request_heads

    def __str__(self) -> str:
        artifact_heads = (
                "[" + ", ".join(map(lambda a: str(a), self.artifact_heads)) + "]") if self.artifact_heads else None
        app_heads = ("[" + ", ".join(map(lambda a: str(a), self.app_heads)) + "]") if self.app_heads else None
        request_heads = "[" + ", ".join(
            map(lambda e: _quoted(str(e)), self.request_heads)) + "]" if self.request_heads else None
        return f'Run(repo_address={self.repo_address}, ' \
               f'run_name="{self.run_name}", ' \
               f'workflow_name={_quoted(self.workflow_name)}, ' \
               f'provider_name="{self.provider_name}", ' \
               f'local_repo_user_name={_quoted(self.local_repo_user_name)}, ' \
               f'status=JobStatus.{self.status.name}, ' \
               f'submitted_at={self.submitted_at}, ' \
               f'artifact_heads={artifact_heads}, ' \
               f'tag_name={_quoted(self.tag_name)}, ' \
               f'app_heads={app_heads}, ' \
               f'request_heads={request_heads})'
