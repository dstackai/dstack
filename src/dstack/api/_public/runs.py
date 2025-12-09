import base64
import queue
import tempfile
import threading
import time
from abc import ABC
from collections.abc import Iterator
from contextlib import contextmanager
from copy import copy
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Dict, Iterable, List, Optional, Union
from urllib.parse import urlencode, urlparse

from websocket import WebSocketApp

import dstack.api as api
from dstack._internal.core.consts import DSTACK_RUNNER_HTTP_PORT, DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ClientError, ConfigurationError, ResourceNotExistsError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    PortMapping,
    ServiceConfiguration,
)
from dstack._internal.core.models.files import FileArchiveMapping
from dstack._internal.core.models.profiles import (
    Profile,
)
from dstack._internal.core.models.repos.base import Repo
from dstack._internal.core.models.repos.virtual import VirtualRepo
from dstack._internal.core.models.runs import (
    Job,
    JobSpec,
    JobStatus,
    RunPlan,
    RunSpec,
    RunStatus,
    get_service_port,
)
from dstack._internal.core.models.runs import Run as RunModel
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.logs import URLReplacer
from dstack._internal.core.services.ssh.attach import SSHAttach
from dstack._internal.core.services.ssh.key_manager import UserSSHKeyManager
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.utils.common import get_or_error, make_proxy_url
from dstack._internal.utils.files import create_file_archive
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike
from dstack.api._public.common import Deprecated
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
        run: RunModel,
        ports_lock: Optional[PortsLock] = None,
        ssh_identity_file: Optional[PathLike] = None,
    ):
        self._api_client = api_client
        self._project = project
        self._run = run
        self._ports_lock: Optional[PortsLock] = ports_lock
        self._ssh_attach: Optional[SSHAttach] = None
        if ssh_identity_file is not None:
            logger.warning(
                "[code]ssh_identity_file[/code] in [code]Run[/code] is deprecated and ignored; will be removed"
                " since 0.19.40"
            )

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

    def _attached_logs(self, start_time: Optional[datetime] = None) -> Iterable[bytes]:
        q = queue.Queue()
        _done = object()

        def ws_thread():
            try:
                logger.debug("Starting WebSocket logs for %s", self.name)
                ws.run_forever(ping_interval=60)
            finally:
                logger.debug("WebSocket logs are done for %s", self.name)
                q.put(_done)

        url = f"ws://localhost:{self.ports[DSTACK_RUNNER_HTTP_PORT]}/logs_ws"
        query_params = {}
        if start_time is not None:
            query_params["start_time"] = start_time.isoformat()
        if query_params:
            url = f"{url}?{urlencode(query_params)}"
        ws = WebSocketApp(
            url=url,
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
                get_or_error(get_or_error(self._ssh_attach).service_port): service_port,
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
        replica_num: Optional[int] = None,
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
            yield from self._attached_logs(start_time=start_time)
        else:
            job = self._find_job(replica_num=replica_num, job_num=job_num)
            if job is None:
                return []
            next_token = None
            while True:
                resp = self._api_client.logs.poll(
                    project_name=self._project,
                    body=PollLogsRequest(
                        run_name=self.name,
                        job_submission_id=job.job_submissions[-1].id,
                        start_time=start_time,
                        end_time=None,
                        descending=False,
                        limit=1000,
                        diagnose=diagnose,
                        next_token=next_token,
                    ),
                )
                for log in resp.logs:
                    yield base64.b64decode(log.message)
                next_token = resp.next_token
                if next_token is None:
                    break

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
        replica_num: Optional[int] = None,
        job_num: int = 0,
    ) -> bool:
        """
        Establish an SSH tunnel to the instance and update SSH config

        Args:
            ssh_identity_file: SSH keypair to access instances.
            replica_num: replica_num or None to attach to any running replica.

        Raises:
            dstack.api.PortUsedError: If ports are in use or the run is attached by another process.
        """
        if not ssh_identity_file:
            config_manager = ConfigManager()
            key_manager = UserSSHKeyManager(self._api_client, config_manager.dstack_ssh_dir)
            user_key = key_manager.get_user_key()
            if user_key.public_key == self._run.run_spec.ssh_key_pub:
                ssh_identity_file = user_key.private_key_path
            else:
                if config_manager.dstack_key_path.exists():
                    logger.debug(f"Using legacy [code]{config_manager.dstack_key_path}[/code].")
                    ssh_identity_file = config_manager.dstack_key_path
                else:
                    raise ConfigurationError(
                        f"User SSH key doesn't match; default SSH key ({config_manager.dstack_key_path}) doesn't exist"
                    )
        ssh_identity_file = str(ssh_identity_file)

        job = self._find_job(replica_num=replica_num, job_num=job_num)
        if job is None:
            replica_repr = replica_num if replica_num is not None else "<any running>"
            raise ClientError(f"Failed to find replica={replica_repr} job={job_num}")
        replica_num = job.job_spec.replica_num

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

            service_port = None
            if isinstance(self._run.run_spec.configuration, ServiceConfiguration):
                service_port = get_service_port(job.job_spec, self._run.run_spec.configuration)

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
                service_port=service_port,
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

    def _find_job(self, replica_num: Optional[int], job_num: int) -> Optional[Job]:
        for j in self._run.jobs:
            if (
                replica_num is not None
                and j.job_spec.replica_num == replica_num
                or replica_num is None
                and j.job_submissions[-1].status == JobStatus.RUNNING
            ) and j.job_spec.job_num == job_num:
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
        repo_dir: Union[Deprecated, str, None] = Deprecated.PLACEHOLDER,
        ssh_identity_file: Optional[PathLike] = None,
    ) -> RunPlan:
        """
        Get a run plan.
        Use this method to see the run plan before applying the configuration.

        Args:
            configuration (Union[Task, Service, DevEnvironment]): The run configuration.
            repo (Union[RemoteRepo, VirtualRepo, None]):
                The repo to use for the run. Pass `None` if repo is not needed.
            profile: The profile to use for the run.
            configuration_path: The path to the configuration file. Omit if the configuration
                is not loaded from a file.
            ssh_identity_file: Path to the private SSH key file. The corresponding public key
                (`.pub` file) is read and included in the run plan, allowing SSH access to the instances.
                If the `.pub` file does not exist, it is generated automatically.
                If ssh_identity_file is not specified, the user key is used.

        Returns:
            Run plan.
        """
        if repo is None:
            repo = VirtualRepo()
            repo_code_hash = None
        else:
            with _prepare_code_file(repo) as (_, repo_code_hash):
                pass

        if repo_dir is not Deprecated.PLACEHOLDER:
            logger.warning(
                "The repo_dir argument is deprecated, ignored, and will be removed soon."
                " Remove it and use the repos[].path configuration property instead."
            )
        if configuration.repos:
            repo_dir = configuration.repos[0].path
        else:
            repo_dir = None

        self._validate_configuration_files(configuration, configuration_path)
        file_archives: list[FileArchiveMapping] = []
        for file_mapping in configuration.files:
            with tempfile.TemporaryFile("w+b") as fp:
                try:
                    archive_hash = create_file_archive(file_mapping.local_path, fp)
                except OSError as e:
                    raise ClientError(f"failed to archive '{file_mapping.local_path}': {e}") from e
                fp.seek(0)
                archive = self._api_client.files.upload_archive(hash=archive_hash, fp=fp)
            file_archives.append(FileArchiveMapping(id=archive.id, path=file_mapping.path))

        if ssh_identity_file:
            ssh_key_pub = Path(ssh_identity_file).with_suffix(".pub").read_text()
        else:
            ssh_key_pub = None  # using the server-managed user key
        run_spec = RunSpec(
            run_name=configuration.name,
            repo_id=repo.repo_id,
            repo_data=repo.run_repo_data,
            repo_code_hash=repo_code_hash,
            repo_dir=repo_dir,
            file_archives=file_archives,
            configuration_path=configuration_path,
            configuration=configuration,
            profile=profile,
            ssh_key_pub=ssh_key_pub,
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
            repo (Union[RemoteRepo, VirtualRepo, None]):
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
            with _prepare_code_file(repo) as (fp, repo_code_hash):
                self._api_client.repos.upload_code(
                    project_name=self._project,
                    repo_id=repo.repo_id,
                    code_hash=repo_code_hash,
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
        ssh_identity_file: Optional[PathLike] = None,
    ) -> Run:
        """
        Apply the run configuration.
        Use this method to apply configurations without getting a run plan first.

        Args:
            configuration (Union[Task, Service, DevEnvironment]): The run configuration.
            repo (Union[RemoteRepo, VirtualRepo, None]):
                The repo to use for the run. Pass `None` if repo is not needed.
            profile: The profile to use for the run.
            configuration_path: The path to the configuration file. Omit if the configuration is not loaded from a file.
            reserve_ports: Reserve local ports before applying. Use if you'll attach to the run.
            ssh_identity_file: Path to the private SSH key file. The corresponding public key
                (`.pub` file) is read and included in the run plan, allowing SSH access to the instances.
                If the `.pub` file does not exist, it is generated automatically.
                If ssh_identity_file is not specified, the user key is used.

        Returns:
            Submitted run.
        """
        run_plan = self.get_run_plan(
            configuration=configuration,
            repo=repo,
            profile=profile,
            configuration_path=configuration_path,
            ssh_identity_file=ssh_identity_file,
        )
        run = self.apply_plan(
            run_plan=run_plan,
            repo=repo,
            reserve_ports=reserve_ports,
        )
        return run

    def list(self, all: bool = False, limit: Optional[int] = None) -> List[Run]:
        """
        List runs.

        Args:
            all: Show all runs (active and finished) if `True`.
            limit: Limit the number of runs to return. Must be less than 100.

        Returns:
            List of runs.
        """
        # Return only one page of latest runs (<=100). Returning all the pages may be costly.
        # TODO: Consider introducing `since` filter with a reasonable default.
        only_active = not all and limit is None
        runs = self._api_client.runs.list(
            project_name=self._project,
            repo_id=None,
            only_active=only_active,
            limit=limit or 100,
            job_submissions_limit=1,
        )
        if only_active and len(runs) == 0:
            runs = self._api_client.runs.list(
                project_name=self._project,
                repo_id=None,
                limit=1,
            )
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
            run,
        )

    def _model_to_submitted_run(self, run: RunModel, ports_lock: Optional[PortsLock]) -> Run:
        return Run(
            self._api_client,
            self._project,
            run,
            ports_lock,
        )

    def _validate_configuration_files(
        self, configuration: AnyRunConfiguration, configuration_path: Optional[PathLike]
    ) -> None:
        """
        Expands, normalizes and validates local paths specified in
        the `files` configuration property.
        """
        base_dir: Optional[Path] = None
        if configuration_path is not None:
            base_dir = Path(configuration_path).expanduser().resolve().parent
        for file_mapping in configuration.files:
            path = Path(file_mapping.local_path).expanduser()
            if not path.is_absolute():
                if base_dir is None:
                    raise ConfigurationError(
                        f"Path '{path}' is relative but `configuration_path` is not provided"
                    )
                else:
                    path = base_dir / path
            if not path.exists():
                raise ConfigurationError(f"Path '{path}' specified in `files` does not exist")
            file_mapping.local_path = str(path)


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


@contextmanager
def _prepare_code_file(repo: Repo) -> Iterator[tuple[BinaryIO, str]]:
    with tempfile.TemporaryFile("w+b") as fp:
        repo_code_hash = repo.write_code_file(fp)
        fp.seek(0)
        yield fp, repo_code_hash
