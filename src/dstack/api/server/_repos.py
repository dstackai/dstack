from typing import BinaryIO, List, Optional

from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.repos import (
    AnyRepoInfo,
    RemoteRepoCreds,
    RepoHead,
    RepoHeadWithCreds,
)
from dstack._internal.server.schemas.repos import (
    DeleteReposRequest,
    GetRepoRequest,
    SaveRepoCredsRequest,
)
from dstack.api.server._group import APIClientGroup


class ReposAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[RepoHead]:
        resp = self._request(f"/api/project/{project_name}/repos/list")
        return validate_extra_ignore(List[RepoHead], resp.json())

    def get(
        self, project_name: str, repo_id: str, include_creds: Optional[bool] = None
    ) -> RepoHead:
        if include_creds is not None:
            self._logger.warning(
                "`include_creds` argument is deprecated and has no effect, `get()` always returns"
                " the repo without creds. Use `get_with_creds()` to get the repo with creds"
            )
        body = GetRepoRequest(repo_id=repo_id, include_creds=False)
        resp = self._request(f"/api/project/{project_name}/repos/get", body=body.model_dump_json())
        return validate_extra_ignore(RepoHead, resp.json())

    def get_with_creds(self, project_name: str, repo_id: str) -> RepoHeadWithCreds:
        body = GetRepoRequest(repo_id=repo_id, include_creds=True)
        resp = self._request(f"/api/project/{project_name}/repos/get", body=body.model_dump_json())
        return validate_extra_ignore(RepoHeadWithCreds, resp.json())

    def init(
        self,
        project_name: str,
        repo_id: str,
        repo_info: AnyRepoInfo,
        repo_creds: Optional[RemoteRepoCreds] = None,
    ):
        body = SaveRepoCredsRequest(
            repo_id=repo_id,
            repo_info=repo_info,
            repo_creds=repo_creds,
        )
        self._request(f"/api/project/{project_name}/repos/init", body=body.model_dump_json())

    def delete(self, project_name: str, repos_ids: List[str]):
        body = DeleteReposRequest(repos_ids=repos_ids)
        self._request(f"/api/project/{project_name}/repos/delete", body=body.model_dump_json())

    def upload_code(self, project_name: str, repo_id: str, code_hash: str, fp: BinaryIO):
        self._request(
            f"/api/project/{project_name}/repos/upload_code",
            files={"file": (code_hash, fp)},
            params={"repo_id": repo_id},
        )
