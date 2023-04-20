import json
from typing import Dict, Generator, List, Optional
from urllib.parse import urlencode, urlparse, urlunparse

import requests

from dstack.core.artifact import Artifact
from dstack.core.error import BackendError, NoMatchingInstanceError
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import RemoteRepoCredentials, Repo, RepoSpec
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
)


class HubClient:
    def __init__(self, url: str, project: str, token: str, repo: Repo):
        self.url = url
        self.token = token
        self.project = project
        self.repo = repo

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

    def create_run(self) -> str:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/runs/create",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            return resp.text
        resp.raise_for_status()

    def create_job(self, job: Job):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/create",
        )
        resp = _make_hub_request(
            requests.post, host=self.url, url=url, headers=self._headers(), data=job.json()
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def get_job(self, job_id: str) -> Optional[Job]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/get",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=JobsGet(
                repo_spec=RepoSpec.from_repo(self.repo),
                job_id=job_id,
            ).json(),
        )
        if resp.ok:
            json_data = resp.json()
            return Job.parse_obj(json_data)
        resp.raise_for_status()

    def list_jobs(self, run_name: str) -> List[Job]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/list",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=JobsList(repo_spec=RepoSpec.from_repo(self.repo), run_name=run_name).json(),
        )
        if resp.ok:
            body = resp.json()
            return [Job.parse_obj(job) for job in body]
        resp.raise_for_status()

    def run_job(self, job: Job):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/runners/run",
        )
        resp = _make_hub_request(
            requests.post, host=self.url, url=url, headers=self._headers(), data=job.json()
        )
        if resp.ok:
            return
        elif resp.status_code == 400:
            body = resp.json()
            if body["detail"]["code"] == NoMatchingInstanceError.code:
                raise BackendError(body["detail"]["msg"])
        resp.raise_for_status()

    def stop_job(self, job_id: str, abort: bool):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/runners/stop",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=StopRunners(
                repo_spec=RepoSpec.from_repo(self.repo),
                job_id=job_id,
                abort=abort,
            ).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def list_job_heads(self, run_name: Optional[str] = None) -> Optional[List[JobHead]]:
        query = {}
        if run_name is not None:
            query["run_name"] = run_name
        url = _url(
            url=self.url, project=self.project, additional_path=f"/jobs/list/heads", query=query
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            body = resp.json()
            return [JobHead.parse_obj(job) for job in body]
        resp.raise_for_status()

    def delete_job_head(self, job_id: str):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/delete",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=JobsGet(repo_spec=RepoSpec.from_repo(self.repo), job_id=job_id).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def get_tag_head(self, tag_name: str) -> Optional[TagHead]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/{tag_name}",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            return TagHead.parse_obj(resp.json())
        elif resp.status_code == 404:
            return None
        resp.raise_for_status()

    def list_tag_heads(self) -> Optional[List[TagHead]]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/list/heads",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            body = resp.json()
            return [TagHead.parse_obj(tag) for tag in body]
        resp.raise_for_status()

    def add_tag_from_run(
        self,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/add/run",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=AddTagRun(
                repo_spec=RepoSpec.from_repo(self.repo),
                tag_name=tag_name,
                run_name=run_name,
                run_jobs=run_jobs,
            ).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def add_tag_from_local_dirs(
        self,
        tag_name: str,
        local_dirs: List[str],
    ):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/add/path",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=AddTagPath(
                repo_spec=RepoSpec.from_repo(self.repo),
                tag_name=tag_name,
                local_dirs=local_dirs,
            ).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def delete_tag_head(self, tag_head: TagHead):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/{tag_head.tag_name}/delete",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def list_run_heads(
        self,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/runs/list",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RunsList(
                repo_spec=RepoSpec.from_repo(self.repo),
                run_name=run_name,
                include_request_heads=include_request_heads,
            ).json(),
        )
        if resp.ok:
            body = resp.json()
            return [RunHead.parse_obj(run) for run in body]
        resp.raise_for_status()

    def update_repo_last_run_at(self, last_run_at: int):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/repos/update",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=ReposUpdate(
                repo_spec=RepoSpec.from_repo(self.repo),
                last_run_at=last_run_at,
            ).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def get_repos_credentials(self) -> Optional[RemoteRepoCredentials]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/repos/credentials/get",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            json_data = resp.json()
            return RemoteRepoCredentials(**json_data)
        elif resp.status_code == 404:
            return None
        resp.raise_for_status()

    def save_repos_credentials(self, repo_credentials: RemoteRepoCredentials):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/repos/credentials/save",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=SaveRepoCredentials(
                repo_spec=RepoSpec.from_repo(self.repo),
                repo_credentials=repo_credentials,
            ).json(),
        )
        if resp.ok:
            return resp.text
        resp.raise_for_status()

    def list_secret_names(self) -> List[str]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/list",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            return resp.json()
        resp.raise_for_status()

    def get_secret(self, secret_name: str) -> Optional[Secret]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/{secret_name}/get",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            json_data = resp.json()
            return Secret.parse_obj(json_data)
        elif resp.status_code == 404:
            return None
        resp.raise_for_status()

    def add_secret(self, secret: Secret):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/add",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=SecretAddUpdate(
                repo_spec=RepoSpec.from_repo(self.repo),
                secret=secret,
            ).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def update_secret(self, secret: Secret):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/update",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=SecretAddUpdate(
                repo_spec=RepoSpec.from_repo(self.repo),
                secret=secret,
            ).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def delete_secret(self, secret_name: str):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/{secret_name}/delete",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def list_run_artifact_files(self, run_name: str) -> List[Artifact]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/artifacts/list",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=JobsList(repo_spec=RepoSpec.from_repo(self.repo), run_name=run_name).json(),
        )
        if resp.ok:
            artifact_data = resp.json()
            return [Artifact.parse_obj(artifact) for artifact in artifact_data]
        resp.raise_for_status()

    def poll_logs(
        self,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/logs/poll",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=PollLogs(
                repo_spec=RepoSpec.from_repo(self.repo),
                job_heads=job_heads,
                start_time=start_time,
                attached=attached,
            ).json(),
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
        resp.raise_for_status()

    def upload_file(self, dest_path: str) -> Optional[str]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/link/upload",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=LinkUpload(object_key=dest_path).json(),
        )
        if resp.ok:
            return resp.text
        resp.raise_for_status()

    def download_file(self, dest_path: str) -> Optional[str]:
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/link/download",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=LinkUpload(object_key=dest_path).json(),
        )
        if resp.ok:
            return resp.text
        resp.raise_for_status()

    def delete_workflow_cache(self, workflow_name: str):
        url = _url(
            url=self.url,
            project=self.project,
            additional_path=f"/workflows/{workflow_name}/cache/delete",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RepoSpec.from_repo(self.repo).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()


def _url(url: str, project: str, additional_path: str, query: Optional[dict] = None):
    query = {} if query is None else query
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


def _make_hub_request(request_func, host, *args, **kwargs) -> requests.Response:
    try:
        resp: requests.Response = request_func(*args, **kwargs)
        if resp.status_code == 401:
            raise BackendError(f"Invalid hub token")
        elif resp.status_code == 500:
            url = kwargs.get("url")
            raise BackendError(
                f"Got 500 Server Error from hub: {url}. Check hub logs for details."
            )
        return resp
    except requests.ConnectionError:
        raise BackendError(f"Cannot connect to hub at {host}")
