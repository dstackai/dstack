from typing import BinaryIO, List, Optional

from pydantic import parse_obj_as

from dstack._internal.core.models.repos import AnyRepoInfo, RemoteRepoCreds, RepoHead
from dstack._internal.server.schemas.repos import (
    DeleteReposRequest,
    GetRepoRequest,
    SaveRepoCredsRequest,
)
from dstack.api.server._group import APIClientGroup


class ReposAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[RepoHead]:
        resp = self._request(f"/api/project/{project_name}/repos/list")
        return parse_obj_as(List[RepoHead.__response__], resp.json())

    def get(self, project_name: str, repo_id: str, include_creds: bool) -> RepoHead:
        body = GetRepoRequest(repo_id=repo_id, include_creds=include_creds)
        resp = self._request(f"/api/project/{project_name}/repos/get", body=body.json())
        return parse_obj_as(RepoHead.__response__, resp.json())

    def init(
        self,
        project_name: str,
        repo_id: str,
        repo_info: AnyRepoInfo,
        repo_creds: Optional[RemoteRepoCreds] = None,
    ):
        body = SaveRepoCredsRequest(repo_id=repo_id, repo_info=repo_info, repo_creds=repo_creds)
        self._request(f"/api/project/{project_name}/repos/init", body=body.json())

    def delete(self, project_name: str, repos_ids: List[str]):
        body = DeleteReposRequest(repos_ids=repos_ids)
        self._request(f"/api/project/{project_name}/repos/delete", body=body.json())

    def upload_code(self, project_name: str, repo_id: str, code_hash: str, fp: BinaryIO):
        self._request(
            f"/api/project/{project_name}/repos/upload_code",
            files={"file": (code_hash, fp)},
            params={"repo_id": repo_id},
        )
