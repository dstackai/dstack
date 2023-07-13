from datetime import datetime
from typing import Dict, Generator, List, Optional
from urllib.parse import urlencode, urlparse, urlunparse

import requests

from dstack._internal.core.artifact import Artifact
from dstack._internal.core.build import BuildNotFoundError
from dstack._internal.core.error import NoMatchingInstanceError
from dstack._internal.core.job import Job, JobHead
from dstack._internal.core.log_event import LogEvent
from dstack._internal.core.plan import RunPlan
from dstack._internal.core.repo import RemoteRepoCredentials, Repo, RepoHead, RepoSpec
from dstack._internal.core.run import RunHead
from dstack._internal.core.secret import Secret
from dstack._internal.core.tag import TagHead
from dstack._internal.hub.models import (
    AddTagPath,
    AddTagRun,
    ArtifactsList,
    JobHeadList,
    JobsGet,
    JobsList,
    PollLogs,
    ProjectInfo,
    ReposUpdate,
    RunsGetPlan,
    RunsList,
    SaveRepoCredentials,
    SecretAddUpdate,
    StopRunners,
    StorageLink,
)
from dstack.api.hub.errors import HubClientError


class HubAPIClient:
    def __init__(self, url: str, project: str, token: str, repo: Optional[Repo]):
        self.url = url
        self.token = token
        self.project = project
        self.repo = repo

    @staticmethod
    def _auth(token: str) -> Dict[str, str]:
        if token == "":
            return {}
        headers = {"Authorization": f"Bearer {token}"}
        return headers

    def _headers(self):
        headers = HubAPIClient._auth(token=self.token)
        headers["Content-type"] = "application/json"
        return headers

    def get_project_info(self) -> ProjectInfo:
        resp = _make_hub_request(
            requests.get,
            host=self.url,
            url=f"{self.url}/api/projects/{self.project}",
            headers=self._headers(),
        )
        if resp.ok:
            return ProjectInfo.parse_obj(resp.json())
        resp.raise_for_status()

    def get_run_plan(self, jobs: List[Job]) -> RunPlan:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/runs/get_plan",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=RunsGetPlan(jobs=jobs).json(),
        )
        if resp.ok:
            body = resp.json()
            return RunPlan.parse_obj(body)
        elif resp.status_code == 400:
            body = resp.json()
            if body["detail"]["code"] == NoMatchingInstanceError.code:
                raise HubClientError(body["detail"]["msg"])
            elif body["detail"]["code"] == BuildNotFoundError.code:
                raise HubClientError(body["detail"]["msg"])
        resp.raise_for_status()

    def create_run(self) -> str:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/runs/create",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=self.repo.repo_ref.json(),
        )
        if resp.ok:
            return resp.text
        resp.raise_for_status()

    def create_job(self, job: Job):
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/create",
        )
        resp = _make_hub_request(
            requests.post, host=self.url, url=url, headers=self._headers(), data=job.json()
        )
        resp.raise_for_status()
        job.hub_user_name = resp.json()["hub_user_name"]

    def get_job(self, job_id: str) -> Optional[Job]:
        url = _project_url(
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
                repo_id=self.repo.repo_id,
                job_id=job_id,
            ).json(),
        )
        if resp.ok:
            json_data = resp.json()
            return Job.parse_obj(json_data)
        resp.raise_for_status()

    def list_jobs(self, run_name: str) -> List[Job]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/list",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=JobsList(repo_id=self.repo.repo_id, run_name=run_name).json(),
        )
        if resp.ok:
            body = resp.json()
            return [Job.parse_obj(job) for job in body]
        resp.raise_for_status()

    def run_job(self, job: Job):
        url = _project_url(
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
                raise HubClientError(body["detail"]["msg"])
            elif body["detail"]["code"] == BuildNotFoundError.code:
                raise HubClientError(body["detail"]["msg"])
        resp.raise_for_status()

    def stop_job(self, job_id: str, abort: bool):
        url = _project_url(
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
                repo_id=self.repo.repo_id,
                job_id=job_id,
                abort=abort,
            ).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def list_job_heads(self, run_name: Optional[str] = None) -> Optional[List[JobHead]]:
        url = _project_url(url=self.url, project=self.project, additional_path=f"/jobs/list/heads")
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=JobHeadList(repo_id=self.repo.repo_id, run_name=run_name).json(),
        )
        if resp.ok:
            body = resp.json()
            return [JobHead.parse_obj(job) for job in body]
        resp.raise_for_status()

    def delete_job_head(self, job_id: str):
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/jobs/delete",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=JobsGet(repo_id=self.repo.repo_id, job_id=job_id).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def get_tag_head(self, tag_name: str) -> Optional[TagHead]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/{tag_name}",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=self.repo.repo_ref.json(),
        )
        if resp.ok:
            return TagHead.parse_obj(resp.json())
        elif resp.status_code == 404:
            return None
        resp.raise_for_status()

    def list_tag_heads(self) -> Optional[List[TagHead]]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/list/heads",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=self.repo.repo_ref.json(),
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
        url = _project_url(
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
                repo_id=self.repo.repo_id,
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
        # url = _project_url(
        #     url=self.url,
        #     project=self.project,
        #     additional_path=f"/tags/add/path",
        # )
        # resp = _make_hub_request(
        #     requests.post,
        #     host=self.url,
        #     url=url,
        #     headers=self._headers(),
        #     data=AddTagPath(
        #         repo_spec=RepoSpec.from_repo(self.repo),
        #         tag_name=tag_name,
        #         local_dirs=local_dirs,
        #     ).json(),
        # )
        # if resp.ok:
        #     return
        # resp.raise_for_status()
        raise NotImplementedError()

    def delete_tag_head(self, tag_head: TagHead):
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/tags/{tag_head.tag_name}/delete",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=self.repo.repo_ref.json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def list_run_heads(
        self,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        url = _project_url(
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
                repo_id=self.repo.repo_id,
                run_name=run_name,
                include_request_heads=include_request_heads,
            ).json(),
        )
        if resp.ok:
            body = resp.json()
            return [RunHead.parse_obj(run) for run in body]
        resp.raise_for_status()

    def update_repo_last_run_at(self, last_run_at: int):
        url = _project_url(
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

    def list_repo_heads(self) -> List[RepoHead]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/repos/heads/list",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
        )
        if resp.ok:
            return [RepoHead.parse_obj(e) for e in resp.json()]
        resp.raise_for_status()

    def get_repos_credentials(self) -> Optional[RemoteRepoCredentials]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/repos/credentials/get",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=self.repo.repo_ref.json(),
        )
        if resp.ok:
            json_data = resp.json()
            return RemoteRepoCredentials(**json_data)
        elif resp.status_code == 404:
            return None
        resp.raise_for_status()

    def save_repos_credentials(self, repo_credentials: RemoteRepoCredentials):
        url = _project_url(
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
                repo_id=self.repo.repo_id,
                repo_credentials=repo_credentials,
            ).json(),
        )
        if resp.ok:
            return resp.text
        resp.raise_for_status()

    def list_secret_names(self) -> List[str]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/list",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=self.repo.repo_ref.json(),
        )
        if resp.ok:
            return resp.json()
        resp.raise_for_status()

    def get_secret(self, secret_name: str) -> Optional[Secret]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/{secret_name}/get",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=self.repo.repo_ref.json(),
        )
        if resp.ok:
            json_data = resp.json()
            return Secret.parse_obj(json_data)
        elif resp.status_code == 404:
            return None
        resp.raise_for_status()

    def add_secret(self, secret: Secret):
        url = _project_url(
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
                repo_id=self.repo.repo_id,
                secret=secret,
            ).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def update_secret(self, secret: Secret):
        url = _project_url(
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
                repo_id=self.repo.repo_id,
                secret=secret,
            ).json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def delete_secret(self, secret_name: str):
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/secrets/{secret_name}/delete",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=self.repo.repo_ref.json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()

    def list_run_artifact_files(
        self, run_name: str, prefix: str, recursive: bool
    ) -> List[Artifact]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/artifacts/list",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=ArtifactsList(
                repo_id=self.repo.repo_id, run_name=run_name, prefix=prefix, recursive=recursive
            ).json(),
        )
        if resp.ok:
            artifact_data = resp.json()
            return [Artifact.parse_obj(artifact) for artifact in artifact_data]
        resp.raise_for_status()

    def poll_logs(
        self,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime],
        descending: bool,
        diagnose: bool,
    ) -> Generator[LogEvent, None, None]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/logs/poll",
        )
        prev_event_id = None
        while True:
            resp = _make_hub_request(
                requests.post,
                host=self.url,
                url=url,
                headers=self._headers(),
                data=PollLogs(
                    repo_id=self.repo.repo_id,
                    run_name=run_name,
                    start_time=start_time.isoformat(),
                    end_time=end_time.isoformat() if end_time else None,
                    descending=descending,
                    prev_event_id=prev_event_id,
                    diagnose=diagnose,
                ).json(),
            )
            if not resp.ok:
                resp.raise_for_status()
            body = resp.json()
            logs = [LogEvent.parse_obj(e) for e in body]
            if len(logs) == 0:
                return
            yield from logs
            if descending:
                end_time = logs[-1].timestamp
            else:
                start_time = logs[-1].timestamp
            prev_event_id = logs[-1].event_id

    def upload_file(self, dest_path: str) -> Optional[str]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/link/upload",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=StorageLink(object_key=dest_path).json(),
        )
        if resp.ok:
            return resp.text
        resp.raise_for_status()

    def download_file(self, dest_path: str) -> Optional[str]:
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/link/download",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=StorageLink(object_key=dest_path).json(),
        )
        if resp.ok:
            return resp.text
        resp.raise_for_status()

    def delete_configuration_cache(self, configuration_path: str):
        url = _project_url(
            url=self.url,
            project=self.project,
            additional_path=f"/configurations/{configuration_path}/cache/delete",
        )
        resp = _make_hub_request(
            requests.post,
            host=self.url,
            url=url,
            headers=self._headers(),
            data=self.repo.repo_ref.json(),
        )
        if resp.ok:
            return
        resp.raise_for_status()


def _project_url(url: str, project: str, additional_path: str, query: Optional[dict] = None):
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
            raise HubClientError(f"Invalid hub token")
        elif resp.status_code == 500:
            url = kwargs.get("url")
            raise HubClientError(
                f"Got 500 Server Error from hub: {url}. Check server logs for details."
            )
        return resp
    except requests.ConnectionError:
        raise HubClientError(f"Cannot connect to hub at {host}")
