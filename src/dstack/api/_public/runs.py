import base64
import queue
import tempfile
import threading
import time
from abc import ABC
from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union
from urllib.parse import urlparse

from websocket import WebSocketApp

import dstack.api as api
from dstack._internal.core.errors import ConfigurationError, ResourceNotExistsError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import AnyRunConfiguration
from dstack._internal.core.models.pools import Instance
from dstack._internal.core.models.profiles import (
    DEFAULT_RUN_TERMINATION_IDLE_TIME,
    CreationPolicy,
    Profile,
    ProfileRetryPolicy,
    SpotPolicy,
    TerminationPolicy,
)
from dstack._internal.core.models.repos.base import Repo
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import (
    JobSpec,
    PoolInstanceOffers,
    Requirements,
    RunPlan,
    RunSpec,
    RunStatus,
)
from dstack._internal.core.models.runs import Run as RunModel
from dstack._internal.core.services.logs import URLReplacer
from dstack._internal.core.services.ssh.attach import SSHAttach
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike, path_in_dir
from dstack.api.server import APIClient

logger = get_logger(__name__)


class Run(ABC):
    """
    Attributes:
        name: run name
        ports: ports mapping, if run is attached
        backend: backend type
        status: run status
        hostname: instance hostname
    """

    def __init__(
        self,
        api_client: APIClient,
        project: str,
        ssh_identity_file: Optional[PathLike],
        run: RunModel,
        ports_lock: Optional[PortsLock] = None,
    ):
        self._api_client = api_client
        self._project = project
        self._ssh_identity_file = ssh_identity_file
        self._run = run
        self._ports_lock: Optional[PortsLock] = ports_lock
        self._ssh_attach: Optional[SSHAttach] = None

    @property
    def name(self) -> str:
        return self._run.run_spec.run_name

    @property
    def ports(self) -> Optional[Dict[int, int]]:
        if self._ssh_attach is not None:
            return copy(self._ssh_attach.ports)
        return None

    @property
    def backend(self) -> Optional[BackendType]:
        job = self._run.jobs[0]
        return job.job_submissions[-1].job_provisioning_data.backend

    @property
    def status(self) -> RunStatus:
        return self._run.status

    @property
    def hostname(self) -> str:
        return self._run.jobs[0].job_submissions[-1].job_provisioning_data.hostname

    @property
    def service_url(self) -> str:
        if self._run.run_spec.configuration.type != "service":
            raise ValueError("The run is not a service")
        return self._run.service.url

    def _attached_logs(
        self,
    ) -> Iterable[bytes]:
        q = queue.Queue()
        _done = object()

        def ws_thread():
            try:
                logger.debug("Starting WebSocket logs for %s", self.name)
                ws.run_forever()
            finally:
                logger.debug("WebSocket logs are done for %s", self.name)
                q.put(_done)

        ws = WebSocketApp(
            f"ws://localhost:{self.ports[10999]}/logs_ws",
            on_open=lambda _: logger.debug("WebSocket logs are connected to %s", self.name),
            on_close=lambda _, __, ___: logger.debug("WebSocket logs are disconnected"),
            on_message=lambda _, message: q.put(message),
        )
        threading.Thread(target=ws_thread).start()

        ports = self.ports
        hostname = "127.0.0.1"
        secure = False
        if self._run.service is not None:
            url = urlparse(self._run.service.url)
            ports = {
                **ports,
                # we support only default https port
                self._run.run_spec.configuration.port.container_port: url.port or 443,
            }
            hostname = url.hostname
            secure = url.scheme == "https"
        replace_urls = URLReplacer(
            ports=ports,
            app_specs=self._run.jobs[0].job_spec.app_specs,
            hostname=hostname,
            secure=secure,
            ip_address=self.hostname,
        )

        try:
            while True:
                item = q.get()
                if item is _done:
                    break
                yield replace_urls(item)
        finally:
            logger.debug("Closing WebSocket logs for %s", self.name)
            ws.close()

    def logs(
        self,
        start_time: Optional[datetime] = None,
        diagnose: bool = False,
        replica_num: int = 0,
        job_num: int = 0,
    ) -> Iterable[bytes]:
        """
        Iterate through run's log messages

        Args:
            start_time: minimal log timestamp
            diagnose: return runner logs if `True`

        Yields:
            log messages
        """
        if diagnose is False and self._ssh_attach is not None:
            yield from self._attached_logs()
        else:
            job = None
            for j in self._run.jobs:
                if j.job_spec.replica_num == replica_num and j.job_spec.job_num == job_num:
                    job = j
            if job is None:
                return []
            next_start_time = start_time
            while True:
                resp = self._api_client.logs.poll(
                    project_name=self._project,
                    body=PollLogsRequest(
                        run_name=self.name,
                        job_submission_id=job.job_submissions[-1].id,
                        start_time=next_start_time,
                        end_time=None,
                        descending=False,
                        diagnose=diagnose,
                    ),
                )
                if len(resp.logs) == 0:
                    return []
                for log in resp.logs:
                    yield base64.b64decode(log.message)
                next_start_time = resp.logs[-1].timestamp

    def refresh(self):
        """
        Get up-to-date run info
        """
        self._run = self._api_client.runs.get(self._project, self._run.run_spec.run_name)
        logger.debug("Refreshed run %s: %s", self.name, self.status)

    def stop(self, abort: bool = False):
        """
        Terminate the instance and detach

        Args:
            abort: gracefully stop the run if `False`
        """
        self._api_client.runs.stop(self._project, [self.name], abort)
        logger.debug("%s run %s", "Aborted" if abort else "Stopped", self.name)
        self.detach()

    def attach(
        self,
        ssh_identity_file: Optional[PathLike] = None,
    ) -> bool:
        """
        Establish an SSH tunnel to the instance and update SSH config

        Args:
            ssh_identity_file: SSH keypair to access instances

        Raises:
            dstack.api.PortUsedError: If ports are in use or the run is attached by another process.
        """
        ssh_identity_file = ssh_identity_file or self._ssh_identity_file
        if ssh_identity_file is None:
            raise ConfigurationError("SSH identity file is required to attach to the run")
        ssh_identity_file = str(ssh_identity_file)

        if self._ssh_attach is None:
            while self.status in (
                RunStatus.SUBMITTED,
                RunStatus.PENDING,
                RunStatus.PROVISIONING,
            ):
                time.sleep(5)
                self.refresh()
            # If status is done, there is a chance we could read logs from websocket
            if self.status.is_finished() and self.status != RunStatus.DONE:
                return False

            job = self._run.jobs[0]  # TODO(egor-s): pull logs from all replicas?
            provisioning_data = job.job_submissions[-1].job_provisioning_data

            control_sock_path_and_port_locks = SSHAttach.reuse_control_sock_path_and_port_locks(
                run_name=self.name
            )

            if control_sock_path_and_port_locks is None:
                if self._ports_lock is None:
                    self._ports_lock = _reserve_ports(job.job_spec)
                logger.debug(
                    "Attaching to %s (%s: %s)",
                    self.name,
                    provisioning_data.hostname,
                    self._ports_lock.dict(),
                )
            else:
                self._ports_lock = control_sock_path_and_port_locks[1]
                logger.debug(
                    "Reusing the existing tunnel to %s (%s: %s)",
                    self.name,
                    provisioning_data.hostname,
                    self._ports_lock.dict(),
                )

            self._ssh_attach = SSHAttach(
                hostname=self.hostname,
                ssh_port=provisioning_data.ssh_port,
                user=provisioning_data.username,
                id_rsa_path=ssh_identity_file,
                ports_lock=self._ports_lock,
                run_name=self.name,
                dockerized=provisioning_data.dockerized,
                ssh_proxy=provisioning_data.ssh_proxy,
                control_sock_path=control_sock_path_and_port_locks[0]
                if control_sock_path_and_port_locks
                else None,
                local_backend=provisioning_data.backend == BackendType.LOCAL,
            )
            if not control_sock_path_and_port_locks:
                self._ssh_attach.attach()
            self._ports_lock = None

        return True

    def detach(self):
        """
        Stop the SSH tunnel to the instance and update SSH config
        """
        if self._ssh_attach is not None:
            logger.debug("Detaching from %s", self.name)
            self._ssh_attach.detach()
            self._ssh_attach = None

    def __str__(self) -> str:
        return f"<Run '{self.name}'>"

    def __repr__(self) -> str:
        return f"<Run '{self.name}'>"


class RunCollection:
    """
    Operations with runs
    """

    def __init__(
        self,
        api_client: APIClient,
        project: str,
        client: "api.Client",
    ):
        self._api_client = api_client
        self._project = project
        self._client = client

    def submit(
        self,
        configuration: AnyRunConfiguration,
        configuration_path: Optional[str] = None,
        repo: Optional[Repo] = None,
        backends: Optional[List[BackendType]] = None,
        regions: Optional[List[str]] = None,
        instance_types: Optional[List[str]] = None,
        resources: Optional[ResourcesSpec] = None,
        spot_policy: Optional[SpotPolicy] = None,
        retry_policy: Optional[ProfileRetryPolicy] = None,
        max_duration: Optional[Union[int, str]] = None,
        max_price: Optional[float] = None,
        working_dir: Optional[str] = None,
        run_name: Optional[str] = None,
        reserve_ports: bool = True,
    ) -> Run:
        """
        Submit a run

        Args:
            configuration (Union[Task, Service]): A run configuration.
            configuration_path: The path to the configuration file, relative to the root directory of the repo.
            repo (Union[LocalRepo, RemoteRepo, VirtualRepo]): A repo to mount to the run.
            backends: A list of allowed backend for provisioning.
            regions: A list of cloud regions for provisioning.
            resources: The requirements to run the configuration. Overrides the configuration's resources.
            spot_policy: A spot policy for provisioning.
            retry_policy (RetryPolicy): A retry policy.
            max_duration: The max instance running duration in seconds.
            max_price: The max instance price in dollars per hour for provisioning.
            working_dir: A working directory relative to the repo root directory
            run_name: A desired name of the run. Must be unique in the project. If not specified, a random name is assigned.
            reserve_ports: Whether local ports should be reserved in advance.

        Returns:
            submitted run
        """
        if repo is None:
            repo = configuration.get_repo()
            if repo is None:
                raise ConfigurationError("Repo is required for this type of configuration")
            # TODO: Add Git credentials to RemoteRepo and if they are set, pass them here to RepoCollection.init
            self._client.repos.init(repo)

        run_plan = self.get_plan(
            configuration=configuration,
            repo=repo,
            configuration_path=configuration_path,
            backends=backends,
            regions=regions,
            instance_types=instance_types,
            resources=resources,
            spot_policy=spot_policy,
            retry_policy=retry_policy,
            max_duration=max_duration,
            max_price=max_price,
            working_dir=working_dir,
            run_name=run_name,
        )
        return self.exec_plan(run_plan, repo, reserve_ports=reserve_ports)

    def get_offers(self, profile: Profile, requirements: Requirements) -> PoolInstanceOffers:
        return self._api_client.runs.get_offers(self._project, profile, requirements)

    def create_instance(self, profile: Profile, requirements: Requirements) -> Instance:
        return self._api_client.runs.create_instance(self._project, profile, requirements)

    def get_plan(
        self,
        configuration: AnyRunConfiguration,
        repo: Repo,
        configuration_path: Optional[str] = None,
        backends: Optional[List[BackendType]] = None,
        regions: Optional[List[str]] = None,
        instance_types: Optional[List[str]] = None,
        resources: Optional[ResourcesSpec] = None,
        spot_policy: Optional[SpotPolicy] = None,
        retry_policy: Optional[ProfileRetryPolicy] = None,
        max_duration: Optional[Union[int, str]] = None,
        max_price: Optional[float] = None,
        working_dir: Optional[str] = None,
        run_name: Optional[str] = None,
        pool_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        creation_policy: Optional[CreationPolicy] = None,
        termination_policy: Optional[TerminationPolicy] = None,
        termination_policy_idle: int = DEFAULT_RUN_TERMINATION_IDLE_TIME,
    ) -> RunPlan:
        # """
        # Get run plan. Same arguments as `submit`
        #
        # Returns:
        #     run plan
        # """
        if working_dir is None:
            working_dir = "."
        elif repo.repo_dir is not None:
            working_dir_path = Path(repo.repo_dir) / working_dir
            if not path_in_dir(working_dir_path, repo.repo_dir):
                raise ConfigurationError("Working directory is outside of the repo")
            working_dir = working_dir_path.relative_to(repo.repo_dir).as_posix()

        if configuration_path is None:
            configuration_path = "(python)"

        if resources is not None:
            configuration = configuration.copy(deep=True)
            configuration.resources = resources

        profile = Profile(
            name="(python)",
            backends=backends,
            regions=regions,
            instance_types=instance_types,
            spot_policy=spot_policy,
            retry_policy=retry_policy,
            max_duration=max_duration,
            max_price=max_price,
            pool_name=pool_name,
            instance_name=instance_name,
            creation_policy=creation_policy,
            termination_policy=termination_policy,
            termination_idle_time=termination_policy_idle,
        )
        run_spec = RunSpec(
            run_name=run_name,
            repo_id=repo.repo_id,
            repo_data=repo.run_repo_data,
            repo_code_hash=None,  # `exec_plan` will fill it
            working_dir=working_dir,
            configuration_path=configuration_path,
            configuration=configuration,
            profile=profile,
            ssh_key_pub=Path(self._client.ssh_identity_file + ".pub").read_text().strip(),
        )
        logger.debug("Getting run plan")
        return self._api_client.runs.get_plan(self._project, run_spec)

    def exec_plan(
        self,
        run_plan: RunPlan,
        repo: Repo,
        reserve_ports: bool = True,
    ) -> Run:
        # """
        # Execute run plan
        #
        # Args:
        #     run_plan: result of `get_plan` call
        #     repo: repo to use for the run
        #     reserve_ports: reserve local ports before submit
        #
        # Returns:
        #     submitted run
        # """
        ports_lock = None
        if reserve_ports:
            # TODO handle multiple jobs
            ports_lock = _reserve_ports(run_plan.job_plans[0].job_spec)

        with tempfile.TemporaryFile("w+b") as fp:
            run_plan.run_spec.repo_code_hash = repo.write_code_file(fp)
            fp.seek(0)
            self._api_client.repos.upload_code(
                self._project, repo.repo_id, run_plan.run_spec.repo_code_hash, fp
            )
        logger.debug("Submitting run spec")
        run = self._api_client.runs.submit(self._project, run_plan.run_spec)
        return self._model_to_submitted_run(run, ports_lock)

    def list(self, all: bool = False) -> List[Run]:
        """
        List runs

        Args:
            all: show all runs (active and finished) if `True`

        Returns:
            list of runs
        """
        runs = self._api_client.runs.list(project_name=self._project, repo_id=None)
        if not all:
            active = [run for run in runs if not run.status.is_finished()]
            if active:
                runs = active
            else:
                runs = runs[:1]  # the most recent finished run
        return [self._model_to_run(run) for run in runs]

    def get(self, run_name: str) -> Optional[Run]:
        """
        Get run by run name

        Args:
            run_name: run name

        Returns:
            The run or `None` if not found
        """
        try:
            run = self._api_client.runs.get(self._project, run_name)
            return self._model_to_run(run)
        except ResourceNotExistsError:
            return None

    def _model_to_run(self, run: RunModel) -> Run:
        return Run(
            self._api_client,
            self._project,
            self._client.ssh_identity_file,
            run,
        )

    def _model_to_submitted_run(self, run: RunModel, ports_lock: Optional[PortsLock]) -> Run:
        return Run(
            self._api_client,
            self._project,
            self._client.ssh_identity_file,
            run,
            ports_lock,
        )


def _reserve_ports(job_spec: JobSpec) -> PortsLock:
    ports = {10999: 0}  # Runner API
    for app in job_spec.app_specs:
        ports[app.port] = app.map_to_port or 0
    logger.debug("Reserving ports: %s", ports)
    return PortsLock(ports).acquire()
