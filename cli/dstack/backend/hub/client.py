from typing import Dict, Optional, List
from urllib.parse import urlunparse
import requests
from dstack.core.artifact import Artifact
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import RepoAddress, RepoCredentials, LocalRepoData, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead
from dstack.hub.models import AddTagRun, AddTagPath


def _url(scheme='', host='', path='', params='', query='', fragment=''):
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
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/repos/credentials")
        try:
            resp = requests.get(url=url, headers=HubClient._auth(token=self.token), json=repo_address.dict())
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
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/repos/credentials")
        try:
            resp = requests.post(url=url, headers=HubClient._auth(token=self.token), json={
                "repo_address": repo_address.dict(),
                "repo_credentials": repo_credentials.dict()
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
            resp = requests.post(url=url, headers=HubClient._auth(token=self.token), json=repo_address.dict())
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
            resp = requests.post(url=url, headers=HubClient._auth(token=self.token), json=job.serialize())
            if resp.ok:
                return resp.text
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return ""
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return ""

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        url = _url(scheme="http", host=f"{self.host}:{self.port}", path=f"api/hub/{self.hub_name}/tags/{tag_name}")
        try:
            resp = requests.get(url=url, headers=HubClient._auth(token=self.token), json=repo_address.dict())
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
            resp = requests.get(url=url, headers=HubClient._auth(token=self.token), json=repo_address.dict())
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
            resp = requests.post(url=url, headers=HubClient._auth(token=self.token), json=AddTagRun(
                repo_address=repo_address,
                tag_name=tag_name,
                run_name=run_name,
                run_jobs=run_jobs,
            ).dict())
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
            resp = requests.post(url=url, headers=HubClient._auth(token=self.token), json=AddTagPath(
                repo_data=repo_data,
                tag_name=tag_name,
                local_dirs=local_dirs,
            ).dict())
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
            resp = requests.post(url=url, headers=HubClient._auth(token=self.token), json=repo_address.dict())
            if resp.ok:
                return None
            if resp.status_code == 401:
                print("Unauthorized. Please set correct token")
                return None
        except requests.ConnectionError:
            print(f"{self.host}:{self.port} connection refused")
        return None
