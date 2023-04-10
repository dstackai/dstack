import json
from typing import Dict, Generator, List, Optional
from urllib.parse import urlencode, urlparse, urlunparse

import requests

from dstack.core.artifact import Artifact
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import LocalRepoData, RepoAddress, RepoCredentials
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead
from dstack.hub.models import (
    AddTagPath,
    AddTagRun,
    JobsGet,
    JobsList,
    LinkUpload,
    PollLogs,
    ReposUpdate,
    RunsList,
    SaveRepoCredentials,
    SecretAddUpdate,
    StopRunners,
    UserRepoAddress,
)


def _url(url: str, project: str, additional_path: str, query: dict = {}):
    unparse_url = urlparse(url=url)
    if additional_path.startswith("/"):
        additional_path = additional_path[1:]

    new_url = urlunparse(
        (
            unparse_url.scheme,
            unparse_url.netloc,
            f"/api/project/{project}/{additional_path}",
            None,
            urlencode(query=query),
            unparse_url.fragment,
        )
    )
    return new_url


class HubClient:
    def __init__(self, url: str, project: str, token: str):
        self.url = url
        self.token = token
        self.project = project

    @staticmethod
    def validate(url: str, project: str, token: str) -> bool:
        url = _url(url=url, project=project, additional_path="/info")
        try:
            resp = requests.get(url=url, headers=HubClient._auth(token=token))
            if resp.ok:
                print(resp.json())
                return True
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return False
        except requests.ConnectionError:
            print(f"{url} connection refused")
        return False

    @staticmethod
    def _auth(token: str) -> Dict[str, str]:
        if token == "":
            return {}
        headers = {"Authorization": f"Bearer {token}"}
        return headers

    def _headers(self):
        headers = HubClient._auth(token=self.token)
        headers["Content-type"] = "application/json"
        return headers

    def get_repos_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/repos/credentials/get",
        )
        try:
            resp = requests.post(url=url, headers=self._headers(), data=repo_address.json())
            if resp.ok:
                json_data = resp.json()
                return RepoCredentials(**json_data)
            elif resp.status_code == 404:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def save_repos_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/repos/credentials/save",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=SaveRepoCredentials(
                    repo_address=repo_address,
                    repo_credentials=repo_credentials,
                ).json(),
            )
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def create_run(self, repo_address: RepoAddress) -> str:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/runs/create",
        )
        try:
            resp = requests.post(url=url, headers=self._headers(), data=repo_address.json())
            if resp.ok:
                return resp.text
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return ""
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return ""

    def create_job(self, job: Job):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/create",
        )
        try:
            resp = requests.post(url=url, headers=self._headers(), data=job.json())
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def run_job(self, job: Job):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/runners/run",
        )
        try:
            resp = requests.post(url=url, headers=self._headers(), data=job.json())
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/runners/stop",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=StopRunners(
                    repo_address=repo_address,
                    job_id=job_id,
                    abort=abort,
                ).json(),
            )
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/{tag_name}",
        )
        try:
            resp = requests.post(url=url, headers=self._headers(), data=repo_address.json())
            if resp.ok:
                return TagHead.parse_obj(resp.json())
            elif resp.status_code == 404:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def list_tag_heads(self, repo_address: RepoAddress) -> Optional[List[TagHead]]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/list/heads",
        )
        try:
            resp = requests.post(url=url, headers=self._headers(), data=repo_address.json())
            if resp.ok:
                body = resp.json()
                return [TagHead.parse_obj(tag) for tag in body]
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def add_tag_from_run(
        self,
        repo_address: RepoAddress,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/add/run",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=AddTagRun(
                    repo_address=repo_address,
                    tag_name=tag_name,
                    run_name=run_name,
                    run_jobs=run_jobs,
                ).json(),
            )
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def add_tag_from_local_dirs(
        self,
        repo_data: LocalRepoData,
        tag_name: str,
        local_dirs: List[str],
    ):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/add/path",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=AddTagPath(
                    repo_data=repo_data,
                    tag_name=tag_name,
                    local_dirs=local_dirs,
                ).json(),
            )
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/{tag_head.tag_name}/delete",
        )
        try:
            resp = requests.post(url=url, headers=self._headers(), data=repo_address.json())
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/repos/update",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=ReposUpdate(
                    repo_address=repo_address,
                    last_run_at=last_run_at,
                ).json(),
            )
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def list_job_heads(
        self, repo_address: RepoAddress, run_name: Optional[str] = None
    ) -> Optional[List[JobHead]]:
        query = {}
        if not (run_name is None):
            query["run_name"] = run_name
        url = _url(
            url=self.url, project=self.project, additional_path=f"/jobs/list/heads", query=query
        )
        try:
            resp = requests.post(url=url, headers=self._headers(), data=repo_address.json())
            if resp.ok:
                body = resp.json()
                return [JobHead.parse_obj(job) for job in body]
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def list_run_heads(
        self,
        repo_address: RepoAddress,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/runs/list",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=RunsList(
                    repo_address=repo_address,
                    run_name=run_name,
                    include_request_heads=include_request_heads,
                ).json(),
            )
            if resp.ok:
                body = resp.json()
                return [RunHead.parse_obj(run) for run in body]
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return []
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return []

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/get",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=JobsGet(
                    repo_address=repo_address,
                    job_id=job_id,
                ).json(),
            )
            if resp.ok:
                json_data = resp.json()
                return Job.parse_obj(json_data)
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/list",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=repo_address.json(),
            )
            if resp.ok:
                json_data = resp.json()
                return json_data
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return []
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return []

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/{secret_name}/get",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=repo_address.json(),
            )
            if resp.ok:
                json_data = resp.json()
                return Secret.parse_obj(json_data)
            elif resp.status_code == 404:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/add",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=SecretAddUpdate(
                    repo_address=repo_address,
                    secret=secret,
                ).json(),
            )
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/update",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=SecretAddUpdate(
                    repo_address=repo_address,
                    secret=secret,
                ).json(),
            )
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/{secret_name}/delete",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=repo_address.json(),
            )
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/list",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=JobsList(repo_address=repo_address, run_name=run_name).json(),
            )
            if resp.ok:
                job_data = resp.json()
                return [Job.parse_obj(job) for job in job_data]
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return []
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return []

    def list_run_artifact_files(self, repo_address: RepoAddress, run_name: str) -> List[Artifact]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/artifacts/list",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=JobsList(repo_address=repo_address, run_name=run_name).json(),
            )
            if resp.ok:
                artifact_data = resp.json()
                return [Artifact.parse_obj(artifact) for artifact in artifact_data]
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return []
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return []

    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/delete",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=JobsGet(repo_address=repo_address, job_id=job_id).json(),
            )
            if resp.ok:
                return None
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/logs/poll",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=PollLogs(
                    repo_address=repo_address,
                    job_heads=job_heads,
                    start_time=start_time,
                    attached=attached,
                ).json(),
                stream=True,
            )
            if resp.ok:
                _braces = 0
                _body = bytearray()
                for chunk in resp.iter_content(chunk_size=128):
                    for b in chunk:
                        if b == 123:
                            _braces += 1
                        elif b == 125:
                            _braces -= 1
                        _body.append(b)

                        if _braces == 0:
                            json_data = json.loads(_body)
                            _body = bytearray()
                            yield LogEvent.parse_obj(json_data)
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def upload_file(self, dest_path: str) -> Optional[str]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/link/upload",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=LinkUpload(object_key=dest_path).json(),
            )
            if resp.ok:
                return resp.text
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def download_file(self, dest_path: str) -> Optional[str]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/link/download",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=LinkUpload(object_key=dest_path).json(),
            )
            if resp.ok:
                return resp.text
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
        return None

    def delete_workflow_cache(self, repo_address: RepoAddress, username: str, workflow_name: str):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/workflows/{workflow_name}/cache/delete",
        )
        try:
            resp = requests.post(
                url=url,
                headers=self._headers(),
                data=UserRepoAddress(username=username, repo_address=repo_address).json(),
            )
            if resp.ok:
                return
            elif resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return
            else:
                resp.raise_for_status()
        except requests.ConnectionError:
            print(f"{self.url} connection refused")
