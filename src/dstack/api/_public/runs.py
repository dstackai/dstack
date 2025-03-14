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
from dstack._internal.core.consts import DSTACK_RUNNER_HTTP_PORT, DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ClientError, ConfigurationError, ResourceNotExistsError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import AnyRunConfiguration, PortMapping
from dstack._internal.core.models.profiles import (
    CreationPolicy,
    Profile,
    ProfileRetryPolicy,
    SpotPolicy,
    TerminationPolicy,
    UtilizationPolicy,
)
from dstack._internal.core.models.repos.base import Repo
from dstack._internal.core.models.repos.virtual import VirtualRepo
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import (
    Job,
    JobSpec,
    RunPlan,
    RunSpec,
    RunStatus,
)
from dstack._internal.core.models.runs import Run as RunModel
from dstack._internal.core.services.logs import URLReplacer
from dstack._internal.core.services.ssh.attach import SSHAttach
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.utils.common import get_or_error, make_proxy_url
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
        return make_proxy_url(
            server_url=self._api_client.base_url,
            proxy_url=self._run.service.url,
        )

    @property
    def service_model(self) -> Optional["ServiceModel"]:
        if self._run.run_spec.configuration.type != "service":
            raise ValueError("The run is not a service")
        if self._run.service.model is None:
            return None
        return ServiceModel(
            name=self._run.service.model.name,
            url=make_proxy_url(
                server_url=self._api_client.base_url,
                proxy_url=self._run.service.model.base_url,
            ),
        )

    def _attached_logs(
        self,
    ) -> Iterable[bytes]:
        q = queue.Queue()
        _done = object()

        def ws_thread():
            try:
                logger.debug("Starting WebSocket logs for %s", self.name)
                ws.run_forever(ping_interval=60)
            finally:
                logger.debug("WebSocket logs are done for %s", self.name)
                q.put(_done)

        ws = WebSocketApp(
            f"ws://localhost:{self.ports[DSTACK_RUNNER_HTTP_PORT]}/logs_ws",
            on_open=lambda _: logger.debug("WebSocket logs are connected to %s", self.name),
            on_close=lambda _, status_code, msg: logger.debug(
                "WebSocket logs are disconnected. status_code: %s; message: %s",
                status_code,
                msg,
            ),
            on_message=lambda _, message: q.put(message),
        )
        threading.Thread(target=ws_thread).start()

        hostname = "127.0.0.1"
        secure = False
        ports = self.ports
        path_prefix = ""
        if self._run.service is not None:
            url = urlparse(self.service_url)
            hostname = url.hostname
            secure = url.scheme == "https"
            service_port = url.port
            if service_port is None:
                service_port = 443 if secure else 80
            ports = {
                **ports,
                self._run.run_spec.configuration.port.container_port: service_port,
            }
            path_prefix = url.path
        replace_urls = URLReplacer(
            ports=ports,
            app_specs=self._run.jobs[0].job_spec.app_specs,
            hostname=hostname,
            secure=secure,
            path_prefix=path_prefix,
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
        Iterate through run's log messages.

        Args:
            start_time: Minimal log timestamp.
            diagnose: Return runner logs if `True`.

        Yields:
            Log messages.
        """
        if diagnose is False and self._ssh_attach is not None:
            yield from self._attached_logs()
        else:
            job = self._find_job(replica_num=replica_num, job_num=job_num)
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
                        limit=1000,
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
        Get up-to-date run info.
        """
        self._run = self._api_client.runs.get(self._project, self._run.run_spec.run_name)
        logger.debug("Refreshed run %s: %s", self.name, self.status)

    def stop(self, abort: bool = False):
        """
        Terminate the instance and detach.

        Args:
            abort: Gracefully stop the run if `False`.
        """
        self._api_client.runs.stop(self._project, [self.name], abort)
        logger.debug("%s run %s", "Aborted" if abort else "Stopped", self.name)
        self.detach()

    def attach(
        self,
        ssh_identity_file: Optional[PathLike] = None,
        bind_address: Optional[str] = None,
        ports_overrides: Optional[List[PortMapping]] = None,
        replica_num: int = 0,
        job_num: int = 0,
    ) -> bool:
        """
        Establish an SSH tunnel to the instance and update SSH config

        Args:
            ssh_identity_file: SSH keypair to access instances.

        Raises:
            dstack.api.PortUsedError: If ports are in use or the run is attached by another process.
        """
        ssh_identity_file = ssh_identity_file or self._ssh_identity_file
        if ssh_identity_file is None:
            raise ConfigurationError("SSH identity file is required to attach to the run")
        ssh_identity_file = str(ssh_identity_file)

        job = self._find_job(replica_num=replica_num, job_num=job_num)
        if job is None:
            raise ClientError(f"Failed to find replica={replica_num} job={job_num}")

        name = self.name
        if replica_num != 0 or job_num != 0:
            name = job.job_spec.job_name

        if self._ssh_attach is not None and name != self._ssh_attach.run_name:
            # This is only a limitation when using the same Run instance via Python API.
            # The CLI can attach to different jobs simultaneously.
            raise ClientError("Cannot attach to different job with active attach. Detach first.")

        # TODO: Check there are no two attaches to the same run with different params

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

            # Reload job
            job = get_or_error(self._find_job(replica_num=replica_num, job_num=job_num))
            latest_job_submission = job.job_submissions[-1]
            provisioning_data = latest_job_submission.job_provisioning_data
            if provisioning_data is None:
                raise ClientError("Failed to attach. The run is not provisioned yet.")

            ports_lock = SSHAttach.reuse_ports_lock(run_name=name)

            if ports_lock is None:
                if self._ports_lock is None:
                    self._ports_lock = _reserve_ports(job.job_spec, ports_overrides)
                logger.debug(
                    "Attaching to %s (%s: %s)",
                    name,
                    provisioning_data.hostname,
                    self._ports_lock.dict(),
                )
            else:
                self._ports_lock = ports_lock
                logger.debug(
                    "Reusing the existing tunnel to %s (%s: %s)",
                    name,
                    provisioning_data.hostname,
                    self._ports_lock.dict(),
                )

            container_ssh_port = DSTACK_RUNNER_SSH_PORT
            runtime_data = latest_job_submission.job_runtime_data
            if runtime_data is not None and runtime_data.ports is not None:
                container_ssh_port = runtime_data.ports.get(container_ssh_port, container_ssh_port)

            # TODO: get login name from runner in case it's not specified in the run configuration
            # (i.e. the default image user is used, and it is not root)
            if job.job_spec.user is not None and job.job_spec.user.username is not None:
                container_user = job.job_spec.user.username
            else:
                container_user = "root"

            self._ssh_attach = SSHAttach(
                hostname=provisioning_data.hostname,
                ssh_port=provisioning_data.ssh_port,
                container_ssh_port=container_ssh_port,
                user=provisioning_data.username,
                container_user=container_user,
                id_rsa_path=ssh_identity_file,
                ports_lock=self._ports_lock,
                run_name=name,
                dockerized=provisioning_data.dockerized,
                ssh_proxy=provisioning_data.ssh_proxy,
                local_backend=provisioning_data.backend == BackendType.LOCAL,
                bind_address=bind_address,
            )
            if not ports_lock:
                self._ssh_attach.attach()
            self._ports_lock = None

        return True

    def detach(self):
        """
        Stop the SSH tunnel to the instance and update SSH config
        """
        if self._ssh_attach is not None:
            logger.debug("Detaching from %s", self._ssh_attach.run_name)
            self._ssh_attach.detach()
            self._ssh_attach = None

    def _find_job(self, replica_num: int, job_num: int) -> Optional[Job]:
        for j in self._run.jobs:
            if j.job_spec.replica_num == replica_num and j.job_spec.job_num == job_num:
                return j
        return None

    def __str__(self) -> str:
        return f"<Run '{self.name}'>"

    def __repr__(self) -> str:
        return f"<Run '{self.name}'>"


class ServiceModel:
    def __init__(self, name: str, url: str) -> None:
        self._name = name
        self._url = url

    @property
    def name(self) -> str:
        return self._name

    @property
    def url(self) -> str:
        return self._url

    def __repr__(self) -> str:
        return f"<ServiceModel '{self.name}'>"


class RunCollection:
    """
    Operations with runs.
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

    def get_run_plan(
        self,
        configuration: AnyRunConfiguration,
        repo: Optional[Repo] = None,
        profile: Optional[Profile] = None,
        configuration_path: Optional[str] = None,
    ) -> RunPlan:
        """
        Get a run plan.
        Use this method to see the run plan before applying the cofiguration.

        Args:
            configuration (Union[Task, Service, DevEnvironment]): The run configuration.
            repo (Union[LocalRepo, RemoteRepo, VirtualRepo, None]):
                The repo to use for the run. Pass `None` if repo is not needed.
            profile: The profile to use for the run.
            configuration_path: The path to the configuration file. Omit if the configuration is not loaded from a file.

        Returns:
            Run plan.
        """
        if repo is None:
            repo = VirtualRepo()

        run_spec = RunSpec(
            run_name=configuration.name,
            repo_id=repo.repo_id,
            repo_data=repo.run_repo_data,
            repo_code_hash=None,  # `apply_plan` will fill it
            working_dir=configuration.working_dir,
            configuration_path=configuration_path,
            configuration=configuration,
            profile=profile,
            ssh_key_pub=Path(self._client.ssh_identity_file + ".pub").read_text().strip(),
        )
        logger.debug("Getting run plan")
        run_plan = self._api_client.runs.get_plan(self._project, run_spec)
        return run_plan

    def apply_plan(
        self,
        run_plan: RunPlan,
        repo: Optional[Repo] = None,
        reserve_ports: bool = True,
    ) -> Run:
        """
        Apply the run plan.
        Use this method to apply run plans returned by `get_run_plan`.

        Args:
            run_plan: The result of `get_run_plan` call.
            repo (Union[LocalRepo, RemoteRepo, VirtualRepo, None]):
                The repo to use for the run. Should be the same repo that is passed to `get_run_plan`.
            reserve_ports: Reserve local ports before applying. Use if you'll attach to the run.

        Returns:
            Submitted run.
        """
        ports_lock = None
        if reserve_ports:
            # TODO handle multiple jobs
            ports_lock = _reserve_ports(run_plan.job_plans[0].job_spec)

        if repo is None:
            repo = VirtualRepo()
        else:
            # Do not upload the diff without a repo (a default virtual repo)
            # since upload_code() requires a repo to be initialized.
            with tempfile.TemporaryFile("w+b") as fp:
                run_plan.run_spec.repo_code_hash = repo.write_code_file(fp)
                fp.seek(0)
                self._api_client.repos.upload_code(
                    project_name=self._project,
                    repo_id=repo.repo_id,
                    code_hash=run_plan.run_spec.repo_code_hash,
                    fp=fp,
                )
        run = self._api_client.runs.apply_plan(self._project, run_plan)
        return self._model_to_submitted_run(run, ports_lock)

    def apply_configuration(
        self,
        configuration: AnyRunConfiguration,
        repo: Optional[Repo] = None,
        profile: Optional[Profile] = None,
        configuration_path: Optional[str] = None,
        reserve_ports: bool = True,
    ) -> Run:
        """
        Apply the run configuration.
        Use this method to apply configurations without getting a run plan first.

        Args:
            configuration (Union[Task, Service, DevEnvironment]): The run configuration.
            repo (Union[LocalRepo, RemoteRepo, VirtualRepo, None]):
                The repo to use for the run. Pass `None` if repo is not needed.
            profile: The profile to use for the run.
            configuration_path: The path to the configuration file. Omit if the configuration is not loaded from a file.
            reserve_ports: Reserve local ports before applying. Use if you'll attach to the run.

        Returns:
            Submitted run.
        """
        run_plan = self.get_run_plan(
            configuration=configuration,
            repo=repo,
            profile=profile,
            configuration_path=configuration_path,
        )
        run = self.apply_plan(
            run_plan=run_plan,
            repo=repo,
            reserve_ports=reserve_ports,
        )
        return run

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
        # """
        # Submit a run

        # Args:
        #     configuration (Union[Task, Service]): A run configuration.
        #     configuration_path: The path to the configuration file, relative to the root directory of the repo.
        #     repo (Union[LocalRepo, RemoteRepo, VirtualRepo]): A repo to mount to the run.
        #     backends: A list of allowed backend for provisioning.
        #     regions: A list of cloud regions for provisioning.
        #     resources: The requirements to run the configuration. Overrides the configuration's resources.
        #     spot_policy: A spot policy for provisioning.
        #     retry_policy (RetryPolicy): A retry policy.
        #     max_duration: The max instance running duration in seconds.
        #     max_price: The max instance price in dollars per hour for provisioning.
        #     working_dir: A working directory relative to the repo root directory
        #     run_name: A desired name of the run. Must be unique in the project. If not specified, a random name is assigned.
        #     reserve_ports: Whether local ports should be reserved in advance.

        # Returns:
        #     Submitted run.
        # """
        logger.warning("The submit() method is deprecated in favor of apply_configuration().")
        if repo is None:
            repo = VirtualRepo()
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

    # Deprecated in favor of get_run_plan()
    def get_plan(
        self,
        configuration: AnyRunConfiguration,
        repo: Optional[Repo] = None,
        configuration_path: Optional[str] = None,
        # Unused profile args are deprecated and removed but
        # kept for signature backward compatibility.
        backends: Optional[List[BackendType]] = None,
        regions: Optional[List[str]] = None,
        instance_types: Optional[List[str]] = None,
        resources: Optional[ResourcesSpec] = None,
        spot_policy: Optional[SpotPolicy] = None,
        retry_policy: Optional[ProfileRetryPolicy] = None,
        utilization_policy: Optional[UtilizationPolicy] = None,
        max_duration: Optional[Union[int, str]] = None,
        max_price: Optional[float] = None,
        working_dir: Optional[str] = None,
        run_name: Optional[str] = None,
        pool_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        creation_policy: Optional[CreationPolicy] = None,
        termination_policy: Optional[TerminationPolicy] = None,
        termination_policy_idle: Optional[Union[str, int]] = None,
        reservation: Optional[str] = None,
        idle_duration: Optional[Union[str, int]] = None,
        stop_duration: Optional[Union[str, int]] = None,
    ) -> RunPlan:
        # """
        # Get run plan. Same arguments as `submit`
        #
        # Returns:
        #     run plan
        # """
        logger.warning("The get_plan() method is deprecated in favor of get_run_plan().")
        if repo is None:
            repo = VirtualRepo()

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

        # TODO: [Andrey] "(python") looks as a hack
        profile = Profile(
            name="(python)",
            backends=backends,
            regions=regions,
            instance_types=instance_types,
            reservation=reservation,
            spot_policy=spot_policy,
            retry=None,
            utilization_policy=utilization_policy,
            max_duration=max_duration,
            stop_duration=stop_duration,
            max_price=max_price,
            creation_policy=creation_policy,
            idle_duration=idle_duration,
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
        run_plan = self._api_client.runs.get_plan(self._project, run_spec)
        if run_plan.current_resource is None and run_name is not None:
            # If run_plan.current_resource is missing, this can mean old (0.18.x) server.
            # TODO: Remove in 0.19
            try:
                run_plan.current_resource = self._api_client.runs.get(self._project, run_name)
            except ResourceNotExistsError:
                pass
        return run_plan

    def exec_plan(
        self,
        run_plan: RunPlan,
        repo: Repo,
        reserve_ports: bool = True,
    ) -> Run:
        # """
        # Execute the run plan.

        # Args:
        #     run_plan: Result of `get_run_plan` call.
        #     repo: Repo to use for the run.
        #     reserve_ports: Reserve local ports before submit.

        # Returns:
        #     Submitted run.
        # """
        logger.warning("The exec_plan() method is deprecated in favor of apply_plan().")
        return self.apply_plan(run_plan=run_plan, repo=repo, reserve_ports=reserve_ports)

    def list(self, all: bool = False) -> List[Run]:
        """
        List runs.

        Args:
            all: Show all runs (active and finished) if `True`.

        Returns:
            List of runs.
        """
        # Return only one page of latest runs (<=100). Returning all the pages may be costly.
        # TODO: Consider introducing `since` filter with a reasonable default.
        only_active = not all
        runs = self._api_client.runs.list(
            project_name=self._project,
            repo_id=None,
            only_active=only_active,
        )
        if only_active and len(runs) == 0:
            runs = self._api_client.runs.list(
                project_name=self._project,
                repo_id=None,
            )[:1]
        return [self._model_to_run(run) for run in runs]

    def get(self, run_name: str) -> Optional[Run]:
        """
        Get run by run name.

        Args:
            run_name: Run name.

        Returns:
            The run or `None` if not found.
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


def _reserve_ports(
    job_spec: JobSpec,
    ports_overrides: Optional[List[PortMapping]] = None,
) -> PortsLock:
    if ports_overrides is None:
        ports_overrides = []
    ports = {DSTACK_RUNNER_HTTP_PORT: 0}
    if job_spec.app_specs:
        for app in job_spec.app_specs:
            ports[app.port] = app.map_to_port or 0
    for port_override in ports_overrides:
        if port_override.container_port not in ports:
            raise ClientError(
                f"Cannot override port {port_override.container_port} not exposed by the run"
            )
        ports[port_override.container_port] = port_override.local_port or 0
    logger.debug("Reserving ports: %s", ports)
    return PortsLock(ports).acquire()
