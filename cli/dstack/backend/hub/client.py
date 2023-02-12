from typing import Dict, Optional, List
from urllib.parse import urlunparse

import requests

from dstack.core.artifact import Artifact
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import LocalRepoData, RepoAddress, RepoCredentials, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead
from dstack.hub.models import AddTagRun, AddTagPath, StopRunners, ReposUpdate, RunsList, JobsGet

def _url(scheme="", host="", path="", params="", query="", fragment=""):
    return urlunparse((scheme, host, path, params, query, fragment))


class HubClient:
    def __init__(self, host: str, port: str, token: str, hub_name: str):
        self.host = host
        self.port = port
        self.token = token
        self.hub_name = hub_name

    @staticmethod
    def validate(host: str, token: str, hub_name: str, port: str = "3000") -> bool:
        url = _url(scheme="http", host=f"{host}:{port}", path=f"api/hub/{hub_name}/info")
        try:
            resp = requests.get(url=url, headers=HubClient._auth(token=token))
            if resp.ok:
                print(resp.json())
                return True
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return False
        except requests.ConnectionError:
            print(f"{host}:{port} connection refused")
        return False

    @staticmethod
    def _auth(token: str) -> Dict[str, str]:
        if token == "":
            return {}
        headers = {"Authorization": f"Bearer {token}"}
        return headers

    def get_repos_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        url = _url(
            scheme="http",
            host=f"{self.host}:{self.port}",
            path=f"api/hub/{self.hub_name}/repos/credentials",
        )
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.get(url=url, headers=headers, data=repo_address.json())
            if resp.ok:
                json_data = resp.json()
                return RepoCredentials(
                    protocol=json_data["protocol"],
                    private_key=json_data["private_key"],
                    oauth_token=json_data["oauth_token"],
                )
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def save_repos_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        url = _url(
            scheme="http",
            host=f"{self.host}:{self.port}",
            path=f"api/hub/{self.hub_name}/repos/credentials",
        )
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.post(url=url, headers=headers, data={
                "repo_address": repo_address.json(),
                "repo_credentials": repo_credentials.json()
            })
            if resp.ok:
                return None
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def create_run(self, repo_address: RepoAddress) -> str:
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/runs/create")
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.post(url=url, headers=headers, data=repo_address.json())
            if resp.ok:
                return resp.text
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return ""
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return ""

    def create_job(self, job: Job):
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/jobs/create")
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.post(url=url, headers=headers, data=job.json())
            if resp.ok:
                return None
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def run_job(self, job: Job):
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/runners/run")
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.post(url=url, headers=headers, data=job.json())
            if resp.ok:
                return None
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/runners/stop")
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.post(url=url, headers=headers, data=StopRunners(
                repo_address=repo_address,
                job_id=job_id,
                abort=abort,
            ).json())
            if resp.ok:
                return None
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/tags/{tag_name}")
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.get(url=url, headers=headers, data=repo_address.json())
            if resp.ok:
                return TagHead.parse_obj(resp.json())
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def list_tag_heads(self, repo_address: RepoAddress) -> Optional[List[TagHead]]:
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/tags/list/heads")
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.get(url=url, headers=headers, data=repo_address.json())
            if resp.ok:
                body = resp.json()
                return [TagHead.parse_obj(tag) for tag in body]
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def add_tag_from_run(self, repo_address: RepoAddress,
                         tag_name: str,
                         run_name: str,
                         run_jobs: Optional[List[Job]],
                         ):
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/tags/add/run")
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.post(url=url, headers=headers, data=AddTagRun(
                repo_address=repo_address,
                tag_name=tag_name,
                run_name=run_name,
                run_jobs=run_jobs,
            ).json())
            if resp.ok:
                return None
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def add_tag_from_local_dirs(self, repo_data: LocalRepoData,
                                tag_name: str,
                                local_dirs: List[str],
                                ):
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/tags/add/path")
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.post(url=url, headers=headers, data=AddTagPath(
                repo_data=repo_data,
                tag_name=tag_name,
                local_dirs=local_dirs,
            ).json())
            if resp.ok:
                return None
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        url = _url(scheme="http",
                   host=f"{self.host}:{self.port}",
                   path=f"api/hub/{self.hub_name}/tags/{tag_head.tag_name}/delete"
                   )
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.post(url=url, headers=headers, data=repo_address.json())
            if resp.ok:
                return None
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        url = _url(scheme="http",
                   host=f"{self.host}:{self.port}",
                   path=f"api/hub/{self.hub_name}/repos/update"
                   )
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.post(url=url, headers=headers, data=ReposUpdate(
                repo_address=repo_address,
                last_run_at=last_run_at,
            ).json())
            if resp.ok:
                return None
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def list_job_heads(self, repo_address: RepoAddress, run_name: Optional[str] = None) -> Optional[List[JobHead]]:
        query = ""
        if not(run_name is None):
            query = f"run_name={run_name}"
        url = _url(scheme="http",
                   host=f"{self.host}:{self.port}",
                   path=f"api/hub/{self.hub_name}/jobs/list/heads",
                   query=query
                   )
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.get(url=url, headers=headers, data=repo_address.json())
            if resp.ok:
                body = resp.json()
                return [JobHead.parse_obj(job) for job in body]
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None

    def list_run_heads(self,
                       repo_address: RepoAddress,
                       run_name: Optional[str] = None,
                       include_request_heads: bool = True) -> List[RunHead]:
        url = _url(scheme="http",
                   host=f"{self.host}:{self.port}",
                   path=f"api/hub/{self.hub_name}/runs/list",
                   )
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.get(url=url, headers=headers, data=RunsList(
                repo_address=repo_address,
                run_name=run_name,
                include_request_heads=include_request_heads,
            ).json())
            if resp.ok:
                body = resp.json()
                return [RunHead.parse_obj(run) for run in body]
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return []
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return []

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/jobs/get")
        try:
            headers = HubClient._auth(token=self.token)
            headers["Content-type"] = "application/json"
            resp = requests.get(url=url, headers=headers, data=JobsGet(
                repo_address=repo_address,
                job_id=job_id,
            ).json())
            if resp.ok:
                json_data = resp.json()
                return Job.parse_obj(json_data)
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None
