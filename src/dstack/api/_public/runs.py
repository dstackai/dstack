import queue
import tempfile
import threading
import time
from abc import ABC
from copy import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

import requests
import yaml
from websocket import WebSocketApp

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models import configurations
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import ServiceConfiguration as Service
from dstack._internal.core.models.configurations import TaskConfiguration as Task
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.profiles import ProfileResources as Resources
from dstack._internal.core.models.profiles import ProfileRetryPolicy as RetryPolicy
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.repos import LocalRepo, RemoteRepo
from dstack._internal.core.models.runs import JobSpec
from dstack._internal.core.models.runs import JobStatus as RunStatus
from dstack._internal.core.models.runs import Run as RunModel
from dstack._internal.core.models.runs import RunPlan, RunSpec
from dstack._internal.core.services.ssh.attach import SSHAttach
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike, path_in_dir
from dstack.api.server import APIClient

logger = get_logger("dstack.api.runs")


class Run(ABC):
    def __init__(
        self,
        api_client: APIClient,
        project: str,
        ssh_identity_file: PathLike,
        run: RunModel,
    ):
        self._api_client = api_client
        self._project = project
        self._ssh_identity_file = ssh_identity_file
        self._run = run
        self._ports_lock: Optional[PortsLock] = None
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
        return job.job_submissions[-1].job_provisioning_data.backend  # TODO fix model

    @property
    def status(self) -> RunStatus:
        return self._run.status

    @property
    def hostname(self) -> str:
        return self._run.jobs[0].job_submissions[-1].job_provisioning_data.hostname

    def logs(
        self, start_time: datetime = (datetime.now(tz=timezone.utc) - timedelta(days=1))
    ) -> Iterable[bytes]:
        raise NotImplemented()

    def refresh(self):
        """
        Get up-to-date run info
        """
        self._run = self._api_client.runs.get(self._project, self._run.run_spec.run_name)
        logger.debug("Refreshed run %s: %s", self.name, self.status)

    def stop(self, abort: bool = False):
        """
        Terminate the instance and detach
        """
        self._api_client.runs.stop(self._project, [self.name], abort)
        logger.debug("%s run %s", "Aborted" if abort else "Stopped", self.name)
        self.detach()

    def attach(self) -> bool:
        """
        Establish an SSH tunnel to the instance and update SSH config
        """
        if self._ssh_attach is None:
            while self.status in (RunStatus.SUBMITTED, RunStatus.PENDING, RunStatus.PROVISIONING):
                time.sleep(5)
                self.refresh()
            # If status is done, there is a chance we could read logs from websocket
            if self.status.is_finished() and self.status != RunStatus.DONE:
                return False

            if self._ports_lock is None:
                self._ports_lock = _reserve_ports(self._run.jobs[0].job_spec)
            provisioning_data = self._run.jobs[0].job_submissions[-1].job_provisioning_data
            logger.debug(
                "Attaching to %s (%s: %s)",
                self.name,
                provisioning_data.hostname,
                self._ports_lock.dict(),
            )
            self._ssh_attach = SSHAttach(
                hostname=self.hostname,
                ssh_port=provisioning_data.ssh_port,
                user=provisioning_data.username,
                id_rsa_path=self._ssh_identity_file,
                ports_lock=self._ports_lock,
                run_name=self.name,
                dockerized=provisioning_data.dockerized,
            )
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


class SubmittedRun(Run):
    def __init__(
        self,
        api_client: APIClient,
        project: str,
        ssh_identity_file: PathLike,
        run: RunModel,
        ports_lock: PortsLock,
    ):
        super().__init__(api_client, project, ssh_identity_file, run)
        self._ports_lock = ports_lock
        self._ports: Optional[Dict[int, int]] = None

    def logs(self, start_time: datetime = datetime.now() - timedelta(days=1)) -> Iterable[bytes]:
        if self._ssh_attach is not None:
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
            try:
                while True:
                    item = q.get()
                    if item is _done:
                        break
                    yield item
            finally:
                logger.debug("Closing WebSocket logs for %s", self.name)
                ws.close()
        else:
            yield super().logs(start_time)


class RunCollection:
    def __init__(
        self,
        api_client: APIClient,
        project: str,
        repo_dir: PathLike,
        repo: Union[RemoteRepo, LocalRepo],
        ssh_identity_file: PathLike,
    ):
        self._api_client = api_client
        self._project = project
        self._repo_dir = Path(repo_dir)
        self._repo = repo
        self._ssh_identity_file = str(ssh_identity_file)

    def submit(
        self,
        configuration: Optional[Union[Task, Service]] = None,
        configuration_path: Optional[PathLike] = None,
        backends: Optional[List[BackendType]] = None,
        resources: Optional[Resources] = None,
        spot_policy: Optional[SpotPolicy] = None,
        retry_policy: Optional[RetryPolicy] = None,
        max_duration: Optional[Union[int, str]] = None,
        max_price: Optional[float] = None,
        working_dir: Optional[str] = None,
        run_name: Optional[str] = None,
        verify_ports: bool = True,  # TODO rename to reserve_ports
    ) -> SubmittedRun:
        """
        Submit a run
        :param configuration: run configuration. Mutually exclusive with `configuration_path`
        :param configuration_path: run configuration path, relative to `repo_dir`. Mutually exclusive with `configuration`
        :param backends: list of allowed backend for provisioning
        :param resources: minimal resources for provisioning
        :param spot_policy: spot policy for provisioning
        :param retry_policy: retry policy for interrupted jobs
        :param max_duration: max instance running duration in seconds
        :param max_price: max instance price in dollars per hour for provisioning
        :param working_dir: working directory relative to `repo_dir`
        :param run_name: desired run_name. Must be unique in the project
        :param verify_ports: reserve local ports before submit
        :return: submitted run
        """
        run_plan = self.get_plan(
            configuration=configuration,
            configuration_path=configuration_path,
            backends=backends,
            resources=resources,
            spot_policy=spot_policy,
            retry_policy=retry_policy,
            max_duration=max_duration,
            max_price=max_price,
            working_dir=working_dir,
            run_name=run_name,
        )
        return self.exec_plan(run_plan, reserve_ports=verify_ports)

    def get_plan(
        self,
        configuration: Optional[Union[Task, Service]] = None,
        configuration_path: Optional[PathLike] = None,
        backends: Optional[List[BackendType]] = None,
        resources: Optional[Resources] = None,
        spot_policy: Optional[SpotPolicy] = None,
        retry_policy: Optional[RetryPolicy] = None,
        max_duration: Optional[Union[int, str]] = None,
        max_price: Optional[float] = None,
        working_dir: Optional[str] = None,
        run_name: Optional[str] = None,
    ) -> RunPlan:
        """
        Get run plan. Same arguments as `submit`
        """
        if configuration is None and configuration_path is None:
            raise ConfigurationError(
                "Either configuration or configuration_path must be specified"
            )
        if configuration is not None and configuration_path is not None:
            raise ConfigurationError(
                "Either configuration or configuration_path must be specified, not both"
            )

        working_dir = self._repo_dir / (working_dir or ".")
        if not path_in_dir(working_dir, self._repo_dir):
            raise ConfigurationError("Working directory is outside of the repo")

        if configuration_path is None:
            configuration_path = "(python)"
        else:
            configuration_path = self._repo_dir / configuration_path
            if not path_in_dir(configuration_path, self._repo_dir):
                raise ConfigurationError("Configuration path is outside of the repo")
            with open(configuration_path, "r") as f:
                configuration = configurations.parse(yaml.safe_load(f))
            configuration_path = str(configuration_path.relative_to(self._repo_dir))

        profile = Profile(
            name="(python)",
            backends=backends,
            resources=resources or Resources(),
            spot_policy=spot_policy,
            retry_policy=retry_policy,
            max_duration=max_duration,
            max_price=max_price,
        )
        run_spec = RunSpec(
            run_name=run_name,
            repo_id=self._repo.repo_id,
            repo_data=self._repo.run_repo_data,
            repo_code_hash=None,  # upload code before submit
            working_dir=str(working_dir.relative_to(self._repo_dir)),
            configuration_path=str(configuration_path),
            configuration=configuration,
            profile=profile,
            ssh_key_pub=Path(self._ssh_identity_file + ".pub").read_text().strip(),
        )
        logger.debug("Getting run plan")
        return self._api_client.runs.get_plan(self._project, run_spec)

    def exec_plan(self, run_plan: RunPlan, reserve_ports: bool = True) -> SubmittedRun:
        """
        Execute run plan
        :param run_plan: result of `get_plan` call
        :param reserve_ports: reserve local ports before submit
        :return: submitted run
        """
        ports_lock = None
        if reserve_ports:
            # TODO handle multiple jobs
            ports_lock = _reserve_ports(run_plan.job_plans[0].job_spec)

        with tempfile.TemporaryFile("w+b") as fp:
            run_plan.run_spec.repo_code_hash = self._repo.write_code_file(fp)
            fp.seek(0)
            self._api_client.repos.upload_code(
                self._project, self._repo.repo_id, run_plan.run_spec.repo_code_hash, fp
            )
        logger.debug("Submitting run spec")
        run = self._api_client.runs.submit(self._project, run_plan.run_spec)
        return self._model_to_submitted_run(run, ports_lock)

    def list(self, all: bool = False) -> List[Run]:
        """
        List
        """
        # TODO support `all` key
        runs = self._api_client.runs.list(project_name=self._project, repo_id=None)
        return [self._model_to_run(run) for run in runs]

    def get(self, run_name: str) -> Optional[Run]:
        """
        Get run by run name
        """
        try:
            run = self._api_client.runs.get(self._project, run_name)
            return self._model_to_run(run)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code != 404:
                raise
        return None

    def _model_to_run(self, run: RunModel) -> Run:
        return Run(
            self._api_client,
            self._project,
            self._ssh_identity_file,
            run,
        )

    def _model_to_submitted_run(
        self, run: RunModel, ports_lock: Optional[PortsLock]
    ) -> SubmittedRun:
        return SubmittedRun(
            self._api_client,
            self._project,
            self._ssh_identity_file,
            run,
            ports_lock,
        )


def _reserve_ports(job_spec: JobSpec) -> PortsLock:
    ports = {10999: 0}  # Runner API
    for app in job_spec.app_specs:
        ports[app.port] = app.map_to_port or 0
    logger.debug("Reserving ports: %s", ports)
    return PortsLock(ports).acquire()
