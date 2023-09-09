import os
import threading
from abc import ABC
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue
from typing import Generator, List, Optional, Tuple, Union

from dstack._internal.api.runs import list_runs_hub
from dstack._internal.cli.utils.config import config, get_hub_client
from dstack._internal.cli.utils.configuration import get_configurator
from dstack._internal.cli.utils.init import init_repo
from dstack._internal.cli.utils.run import (
    _attach,
    _detach,
    _poll_logs_ws,
    _poll_run_head,
    get_run_plan,
    reserve_ports,
    run_configuration,
)
from dstack._internal.cli.utils.ssh_tunnel import PortsLock
from dstack._internal.configurators.ports import PortUsedError
from dstack._internal.core.configuration import (
    BaseConfiguration,
    RegistryAuth,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.job import Job, JobHead, JobStatus
from dstack._internal.core.profile import (
    GPU,
    BackendType,
    Profile,
    Resources,
    RetryPolicy,
    SpotPolicy,
)
from dstack._internal.core.userconfig import RepoUserConfig
from dstack._internal.hub.schemas import RunInfo
from dstack.api.hub import HubClient

Task = TaskConfiguration
Service = ServiceConfiguration
RunStatus = JobStatus


class RepoCollection:
    _hub_client: HubClient

    def __init__(self, hub_client: HubClient) -> None:
        super().__init__()
        self._hub_client = hub_client

    def init(
        self,
        git_identity_file: Optional[str] = None,
        oauth_token: Optional[str] = None,
        ssh_identity_file: Optional[str] = None,
    ):
        init_repo(self._hub_client, git_identity_file, oauth_token, ssh_identity_file)


class Run(ABC):
    def __init__(
        self,
        hub_client: HubClient,
        repo_user_config: RepoUserConfig,
        run_info: RunInfo,
    ) -> None:
        super().__init__()
        self._hub_client = hub_client
        self._repo_user_config = repo_user_config
        self._run_info = run_info
        self.name = run_info.run_head.run_name
        self._port_locks = None
        self._is_attached = False
        self._ports = None
        self._jobs = None

    def logs(
        self, start_time: datetime = (datetime.now(tz=timezone.utc) - timedelta(days=1))
    ) -> Generator[bytes, None, None]:
        for event in self._hub_client.poll_logs(
            run_name=self._run_info.run_head.run_name, start_time=start_time, diagnose=False
        ):
            yield event.log_message

    def status(self) -> RunStatus:
        return next(_poll_run_head(self._hub_client, self._run_info.run_head.run_name)).status

    def stop(self, abort: bool = False):
        self._hub_client.stop_run(self._run_info.run_head.run_name, terminate=True, abort=abort)
        _detach(self._run_info.run_head.run_name)

    def attach(self):
        if not self._is_attached:
            for _ in _poll_run_head(
                self._hub_client,
                self._run_info.run_head.run_name,
                loop_statuses=[
                    RunStatus.PENDING,
                    RunStatus.SUBMITTED,
                    RunStatus.DOWNLOADING,
                ],
            ):
                pass

            self._jobs = [
                self._hub_client.get_job(job_head.job_id)
                for job_head in self._run_info.run_head.job_heads
            ]
            if self._port_locks is None:
                self._port_locks = reserve_ports(
                    apps=self._jobs[0].app_specs,
                    local_backend=False,
                )
            self._ports = _attach(
                self._hub_client,
                self._run_info,
                self._jobs[0],
                self._repo_user_config.ssh_key_path,
                self._port_locks,
            )
            self._is_attached = True

    def detach(self):
        if self._is_attached:
            _detach(self._run_info.run_head.run_name)
            self._is_attached = False
            self._ports = None
            self._jobs = None

    def __str__(self) -> str:
        return f"<Run '{self.name}'>"

    def __repr__(self) -> str:
        return f"<Run '{self.name}'>"


class SubmittedRun(Run):
    def __init__(
        self,
        hub_client: HubClient,
        repo_user_config: RepoUserConfig,
        run_info: RunInfo,
        port_locks: Tuple[PortsLock, PortsLock],
    ) -> None:
        super().__init__(hub_client, repo_user_config, run_info)
        self._port_locks = port_locks
        self._is_attached = False
        self._jobs: Optional[List[Job]] = None
        self._ports: Optional[dict[int, int]] = None

    def logs(
        self, start_time: datetime = datetime.now() - timedelta(days=1)
    ) -> Generator[bytes, None, None]:
        if self._is_attached:
            queue = Queue()
            job_done = object()

            def poll_logs_light_thread_func():
                def log_handler(message: bytes):
                    queue.put(message)

                try:
                    _poll_logs_ws(self._hub_client, self._jobs[0], self._ports, log_handler)
                finally:
                    queue.put(job_done)

            threading.Thread(
                target=poll_logs_light_thread_func,
            ).start()

            while True:
                item = queue.get()
                if item is job_done:
                    break
                else:
                    yield item
        else:
            return super().logs(start_time)


class RunCollection:
    _hub_client: HubClient

    def __init__(self, hub_client: HubClient, repo_user_config: RepoUserConfig) -> None:
        super().__init__()
        self._hub_client = hub_client
        self._repo_user_config = repo_user_config

    def submit(
        self,
        configuration: Union[Task, Service],
        backends: Optional[List[BackendType]] = None,
        resources: Optional[Resources] = None,
        spot_policy: Optional[SpotPolicy] = None,
        retry_policy: Optional[RetryPolicy] = None,
        max_duration: Optional[Union[int, str]] = None,
        max_price: Optional[float] = None,
        working_dir: Optional[str] = None,
        run_name: Optional[str] = None,
        verify_ports: bool = True,
    ) -> SubmittedRun:
        profile = Profile(
            backends=backends,
            resources=resources or Resources(),
            spot_policy=spot_policy,
            retry_policy=retry_policy or RetryPolicy(),
            max_duration=max_duration,
            max_price=max_price,
        )
        configuration_path = "(python)"
        configurator = get_configurator(
            configuration,
            configuration_path,
            working_dir or ".",
            profile or Profile(),
        )
        run_plan = get_run_plan(self._hub_client, configurator, run_name)
        run_name, jobs, ports_locks = run_configuration(
            self._hub_client,
            configurator,
            run_name,
            run_plan,
            verify_ports,
            [],
            self._repo_user_config,
        )
        run_infos = list_runs_hub(self._hub_client, run_name=run_name)
        run_info = run_infos[0]
        return SubmittedRun(
            self._hub_client,
            self._repo_user_config,
            run_info,
            ports_locks,
        )

    def list(self, all: bool = False) -> List[Run]:
        run_infos = list_runs_hub(self._hub_client, all=all)
        return [Run(self._hub_client, self._repo_user_config, run_info) for run_info in run_infos]

    def get(self, run_name: str) -> Optional[Run]:
        run_infos = list_runs_hub(self._hub_client, run_name=run_name)
        return next(
            iter(
                [Run(self._hub_client, self._repo_user_config, run_info) for run_info in run_infos]
            ),
            None,
        )


class Client:
    _hub_client: HubClient
    repo_dir: os.PathLike
    repos: RepoCollection
    runs: RunCollection

    def __init__(
        self,
        hub_client: HubClient,
        repo_dir: os.PathLike,
        init: bool = True,
        git_identity_file: Optional[str] = None,
        oauth_token: Optional[str] = None,
        ssh_identity_file: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._hub_client = hub_client
        self.repo_dir = str(Path(os.path.expanduser(repo_dir)).resolve())
        self.repos = RepoCollection(hub_client)
        if init:
            self.repos.init(git_identity_file, oauth_token, ssh_identity_file)
        self._repo_user_config = config.repo_user_config(repo_dir)
        self.runs = RunCollection(hub_client, self._repo_user_config)

    @staticmethod
    def from_config(
        repo_dir: os.PathLike, project_name: Optional[str] = None, local_repo: bool = False
    ):
        return Client(
            get_hub_client(project_name=project_name, repo_dir=repo_dir), repo_dir, local_repo
        )


if __name__ == "__main__":
    client = Client.from_config("~/dstack-examples")
    run = client.runs.get("streamlist-hello")
    run.attach()
    print(run)
