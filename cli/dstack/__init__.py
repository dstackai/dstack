import os
import sys
import threading
from abc import ABC
from datetime import datetime, timedelta, timezone
from queue import Queue
from typing import Generator, List, Optional, Tuple

from dstack._internal.api.runs import list_runs_hub
from dstack._internal.cli.utils.config import get_hub_client
from dstack._internal.cli.utils.configuration import get_configurator
from dstack._internal.cli.utils.init import init_repo
from dstack._internal.cli.utils.run import (
    _detach,
    _poll_run_head,
    get_run_plan,
    poll_logs_light,
    run_configuration,
)
from dstack._internal.cli.utils.ssh_tunnel import PortsLock
from dstack._internal.core.configuration import (
    BaseConfiguration,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.job import JobHead, JobStatus
from dstack._internal.core.profile import (
    GPU,
    BackendType,
    Profile,
    Resources,
    RetryPolicy,
    SpotPolicy,
)
from dstack._internal.hub.schemas import RunInfo
from dstack.api.hub import HubClient


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
        run_info: RunInfo,
    ) -> None:
        super().__init__()
        self._hub_client = hub_client
        self._run_info = run_info

    def logs(
        self, start_time: datetime = (datetime.now(tz=timezone.utc) - timedelta(days=1))
    ) -> Generator[bytes, None, None]:
        for event in self._hub_client.poll_logs(
            run_name=self._run_info.run_head.run_name, start_time=start_time, diagnose=False
        ):
            yield event.log_message

    @property
    def status(self) -> JobStatus:
        return next(_poll_run_head(self._hub_client, self._run_info.run_head.run_name)).status

    def stop(self, abort: bool = False):
        self._hub_client.stop_run(self._run_info.run_head.run_name, terminate=True, abort=abort)
        _detach(self._run_info.run_head.run_name)


class SubmittedRun(Run):
    def __init__(
        self,
        hub_client: HubClient,
        run_info: RunInfo,
        job_heads: List[JobHead],
        ssh_key: Optional[str],
        port_locks: Tuple[PortsLock, PortsLock],
        detach: bool,
    ) -> None:
        super().__init__(hub_client, run_info)
        self._job_heads = job_heads
        self._ssh_key = ssh_key
        self._port_locks = port_locks
        self._detach = detach

    def logs(
        self, start_time: datetime = datetime.now() - timedelta(days=1)
    ) -> Generator[bytes, None, None]:
        if not self._detach:
            for _ in _poll_run_head(
                self._hub_client,
                self._run_info.run_head.run_name,
                loop_statuses=[
                    JobStatus.PENDING,
                    JobStatus.SUBMITTED,
                    JobStatus.DOWNLOADING,
                ],
            ):
                pass

            queue = Queue()
            job_done = object()

            def poll_logs_light_thread_func():
                def log_handler(message: bytes):
                    queue.put(message)

                try:
                    poll_logs_light(
                        self._hub_client,
                        self._run_info,
                        self._job_heads,
                        self._ssh_key,
                        self._port_locks,
                        log_handler,
                    )
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

    def __init__(self, hub_client: HubClient) -> None:
        super().__init__()
        self._hub_client = hub_client

    def submit(
        self,
        configuration: BaseConfiguration,
        profile: Optional[Profile],
        working_dir: Optional[str] = None,
        run_name: Optional[str] = None,
        detach: bool = False,
    ) -> Run:
        configuration_path = "(python)"
        configurator = get_configurator(
            configuration,
            configuration_path,
            working_dir or ".",
            profile or Profile(name="default"),
        )
        repo_user_config, run_plan = get_run_plan(self._hub_client, configurator, run_name)
        run_name, jobs, ports_locks = run_configuration(
            self._hub_client, configurator, run_name, run_plan, detach, [], repo_user_config
        )
        run_infos = list_runs_hub(self._hub_client, run_name=run_name)
        run_info = run_infos[0]
        ssh_key = repo_user_config.ssh_key_path
        return SubmittedRun(self._hub_client, run_info, jobs, ssh_key, ports_locks, detach)

    def list(self, run_name: Optional[str] = None, all: bool = False) -> List[Run]:
        run_infos = list_runs_hub(self._hub_client, run_name=run_name, all=all)
        return [Run(self._hub_client, run_info) for run_info in run_infos]


class Client:
    _hub_client: HubClient
    repos: RepoCollection
    runs: RunCollection

    def __init__(self, hub_client: HubClient) -> None:
        super().__init__()
        self._hub_client = hub_client
        self.repos = RepoCollection(hub_client)
        self.runs = RunCollection(hub_client)

    @staticmethod
    def from_config(repo_dir: os.PathLike, project_name: Optional[str] = None):
        return Client(get_hub_client(project_name=project_name, repo_dir=repo_dir))
