import re
import shlex
import uuid
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Any, List, Optional

import gpuhunt
import paramiko
from gpuhunt.providers.lium import LiumProvider

from dstack._internal.core.backends.base.authorized_keys import build_authorized_keys
from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithFilteredOffersCached,
    ComputeWithVolumeSupport,
    generate_unique_instance_name_for_job,
    generate_unique_volume_name,
    get_docker_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.lium.api_client import LiumAPIClient, LiumAPIError
from dstack._internal.core.backends.lium.models import LiumConfig
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import (
    ComputeError,
    NoCapacityError,
    NotYetTerminated,
    ProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel, validate_json_extra_ignore
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    SSHConnectionParams,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import (
    LiumVolumeConfiguration,
    Volume,
    VolumeMountPoint,
    VolumeProvisioningData,
)
from dstack._internal.utils.common import get_current_datetime, get_or_error
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import convert_ssh_key_to_pem, pkey_from_str

logger = get_logger(__name__)

MAX_INSTANCE_NAME_LEN = 63
SSH_TIMEOUT_SECONDS = 15
BOOTSTRAP_DIR = "/root/.dstack-lium"
TERMINAL_POD_STATES = {
    "STOPPED",
    "FAILED",
    "CREATION_FAILED",
    "BROKEN",
    "REBOOT_FAILED",
    "DELETING",
    "DELETED",
}
NO_CAPACITY_CODES = {
    "node_not_found",
    "node_rent_in_progress",
    "node_not_verified",
    "node_unavailable",
    "node_paused_by_provider",
    "provider_banned",
    "node_below_bandwidth_floor",
    "gpu_count_invalid",
    "gpu_split_not_allowed",
    "no_executor_matches_spec",
}


class LiumCompute(ComputeWithFilteredOffersCached, ComputeWithVolumeSupport, Compute):
    def __init__(self, config: LiumConfig):
        super().__init__()
        self.config = config
        self.api_client = LiumAPIClient(config.creds.api_key)
        self._catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self._catalog.add_provider(LiumProvider())

    def get_offers_by_requirements(
        self, requirements: Requirements, full_offers: bool, unallocated_resources: bool
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.LIUM,
            locations=self.config.regions or None,
            requirements=requirements,
            catalog=self._catalog,
        )
        return [
            offer.with_availability(
                availability=InstanceAvailability.AVAILABLE,
                instance_runtime=InstanceRuntime.RUNNER,
            )
            for offer in offers
        ]

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
        placement_group: Optional[PlacementGroup],
        requirements: Requirements,
        extra_authorized_keys: list[str],
    ) -> JobProvisioningData:
        image_name = job.job_spec.image_name
        if not image_name or re.search(r"\s", image_name):
            raise ComputeError("Invalid Lium container image name")
        volume_commands = _get_volume_commands(run, job, volumes)
        instance_name = generate_unique_instance_name_for_job(
            run, job, max_length=MAX_INSTANCE_NAME_LEN
        )
        commands = get_docker_commands(
            build_authorized_keys(project_ssh_public_key, extra_authorized_keys),
            pre_runner_commands=volume_commands,
        )
        data = LiumInstanceBackendData(
            pod_name=instance_name,
            executor_id=instance_offer.instance.name,
            startup_command=" && ".join(commands),
        )
        if job.job_spec.registry_auth is not None:
            auth = job.job_spec.registry_auth
            try:
                credential = self.api_client.create_docker_credential(
                    {"docker_username": auth.username, "docker_password": auth.password}
                )
                data.credential_id = _resource_id(credential)
            except LiumAPIError as e:
                if not _is_definitive_error(e):
                    # Credentials have neither a name nor idempotent creation. Never
                    # recover/delete someone else's record by matching only its username.
                    raise ComputeError(
                        "Lium registry credential creation could not be confirmed. "
                        "Check Docker credentials in Lium before retrying."
                    ) from e
                raise
        try:
            data.template_id = self._create_template(
                {
                    "name": instance_name,
                    # Follow the official SDK: Lium splits the complete image reference.
                    "docker_image": image_name,
                    "docker_image_tag": "",
                    "docker_image_digest": "",
                    "entrypoint": "/bin/sh",
                    "startup_commands": "-c 'exec sleep infinity'",
                    "internal_ports": [22, DSTACK_RUNNER_SSH_PORT],
                    "volumes": ["/root"],
                    "is_private": True,
                    "supports_docker": False,
                    "supports_volume_encryption": False,
                    "docker_credential_id": data.credential_id,
                }
            )
        except Exception:
            self._cleanup_failed_resources(data)
            raise
        data.rent_payload = {
            "pod_name": instance_name,
            "template_id": data.template_id,
            "user_public_key": project_ssh_public_key,
            "gpu_count": len(instance_offer.instance.resources.gpus),
            "initial_port_count": 2,
            "enable_jupyter": False,
            # Encrypted /root can become inaccessible after a provider host reboot.
            "enable_volume_encryption": False,
        }
        data.idempotency_key = str(uuid.uuid4())
        data.rent_started_at = get_current_datetime()
        if volumes:
            data.rent_payload["volume_id"] = get_or_error(volumes[0].volume_id)
        pod_id = self._rent(data)
        return JobProvisioningData(
            backend=BackendType.LIUM,
            instance_type=instance_offer.instance,
            instance_id=pod_id or instance_name,
            region=instance_offer.region,
            price=instance_offer.price,
            username="root",
            dockerized=False,
            backend_data=data.model_dump_json(),
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> None:
        data = validate_json_extra_ignore(
            LiumInstanceBackendData, get_or_error(provisioning_data.backend_data)
        )
        if data.rent_failed:
            raise ProvisioningError("Lium rental failed while reconciling its creation response")
        if data.rent_payload is not None:
            pod = self._find_pending_pod(data)
            if pod is None:
                if not self._can_replay_rent(data):
                    return
                pod_id = self._rent(data, reconcile=True)
                provisioning_data.backend_data = data.model_dump_json()
                if pod_id is None:
                    return
                provisioning_data.instance_id = pod_id
                pod = self.api_client.get_pod(pod_id)
            else:
                provisioning_data.instance_id = _resource_id(pod)
                data.rent_payload = None
                data.idempotency_key = None
                provisioning_data.backend_data = data.model_dump_json()
        else:
            pod = self.api_client.get_pod(provisioning_data.instance_id)
        if pod is None:
            raise ProvisioningError("Lium pod was not found")
        status = str(pod.get("status", "")).upper()
        if status in TERMINAL_POD_STATES:
            raise ProvisioningError(f"Lium pod entered {status} state")
        if status != "RUNNING":
            return
        ssh = _get_provider_ssh(pod)
        try:
            _bootstrap_runner(ssh, project_ssh_private_key, data.startup_command)
        except (paramiko.SSHException, OSError):
            # Lium marks RUNNING before its separate SSH bootstrap finishes.
            logger.debug("Waiting for Lium pod %s SSH", provisioning_data.instance_id)
            return
        ports = pod.get("ports_mapping") or {}
        runner_port = ports.get(str(DSTACK_RUNNER_SSH_PORT))
        if runner_port is not None:
            provisioning_data.hostname = ssh.hostname
            provisioning_data.ssh_port = _port(runner_port)
            provisioning_data.ssh_proxy = None
        else:
            provisioning_data.hostname = "localhost"
            provisioning_data.ssh_port = DSTACK_RUNNER_SSH_PORT
            provisioning_data.ssh_proxy = ssh

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        data = validate_json_extra_ignore(LiumInstanceBackendData, get_or_error(backend_data))
        if data.rent_failed:
            self._cleanup_resources(data)
            return
        if data.rent_payload is not None:
            pod = self._find_pending_pod(data)
            if pod is None:
                # Replaying a rent during cancellation could create a new paid pod.
                # An empty list cannot prove an in-flight rent will never commit.
                raise NotYetTerminated(
                    f"Lium rental outcome is uncertain for {data.pod_name}; "
                    "reconcile it in Lium before removing the instance"
                )
            instance_id = _resource_id(pod)
        else:
            pod = self.api_client.get_pod(instance_id)
        if pod is None or pod.get("status") == "DELETED":
            self._cleanup_resources(data)
            return
        if pod.get("status") != "DELETING":
            try:
                self.api_client.delete_pod(instance_id)
            except LiumAPIError as e:
                if e.code != "pod_state_conflict":
                    raise
                current = self.api_client.get_pod(instance_id)
                if current is not None and current.get("status") != "DELETING":
                    raise
        raise NotYetTerminated("Lium pod deletion is in progress")

    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        assert isinstance(volume.configuration, LiumVolumeConfiguration)
        volume_id = get_or_error(volume.configuration.volume_id)
        if self.api_client.get_volume(volume_id) is None:
            raise ComputeError(f"Lium volume {volume_id} not found")
        return _volume_provisioning_data(volume_id)

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        name = generate_unique_volume_name(volume)
        try:
            data = self.api_client.create_volume(name)
        except LiumAPIError as e:
            if _is_definitive_error(e):
                raise
            data = next((v for v in self.api_client.get_volumes() if v.get("name") == name), None)
            if data is None:
                raise
        return _volume_provisioning_data(_resource_id(data))

    def delete_volume(self, volume: Volume) -> None:
        if volume.volume_id is not None:
            self.api_client.delete_volume(volume.volume_id)

    def _create_template(self, payload: dict[str, Any]) -> str:
        try:
            template = self.api_client.create_template(payload)
            return _resource_id(template)
        except LiumAPIError as e:
            if _is_definitive_error(e):
                raise
            for template in self.api_client.get_templates():
                if template.get("name") == payload["name"]:
                    return _resource_id(template)
            logger.warning(
                "Lium template %s creation could not be confirmed; check templates in Lium",
                payload["name"],
            )
            raise

    def _rent(self, data: "LiumInstanceBackendData", *, reconcile: bool = False) -> Optional[str]:
        try:
            response = self.api_client.rent_executor(
                data.executor_id,
                get_or_error(data.rent_payload),
                get_or_error(data.idempotency_key),
            )
            pod_id = _resource_id(response, key="pod_id")
        except LiumAPIError as e:
            if _is_definitive_error(e) and (not reconcile or e.idempotent_replayed):
                data.rent_failed = True
                data.rent_payload = None
                data.idempotency_key = None
                self._cleanup_failed_resources(data)
                if reconcile:
                    # Persist the failed outcome before the next poll raises.
                    return None
                if e.code in NO_CAPACITY_CODES:
                    raise NoCapacityError(f"Lium node is unavailable ({e.code})") from e
                raise
            logger.warning(
                "Lium pod %s creation response is uncertain; reconciling by name",
                data.pod_name,
            )
            return None
        data.rent_payload = None
        data.idempotency_key = None
        return pod_id

    def _find_pending_pod(self, data: "LiumInstanceBackendData") -> Optional[dict[str, Any]]:
        for pod in self.api_client.get_pods():
            if pod.get("pod_name") == data.pod_name and pod.get("executor_id") == data.executor_id:
                return pod
        since = (
            (data.rent_started_at - timedelta(minutes=1)).isoformat()
            if data.rent_started_at is not None
            else None
        )
        # Account events retain pod IDs after they disappear from the live list.
        # This also makes cancellation recovery durable across calls, without
        # process-local state or replaying a rental during deletion.
        for event in self.api_client.get_account_events(since=since):
            if event.get("pod_name") != data.pod_name:
                continue
            pod_id = event.get("pod_id")
            if not isinstance(pod_id, str) or not pod_id:
                continue
            pod = self.api_client.get_pod(pod_id)
            deleted = event.get("to_status") == "DELETED" or (
                event.get("sub_event_type") == "pod-delete.success"
            )
            if pod is None and deleted:
                return {"id": pod_id, "status": "DELETED"}
            if pod is not None and pod.get("executor_id") == data.executor_id:
                return pod
        return None

    def _can_replay_rent(self, data: "LiumInstanceBackendData") -> bool:
        if data.rent_started_at is None:
            return False
        if get_current_datetime() - data.rent_started_at >= timedelta(hours=24):
            return False
        # Older Lium releases may ignore the key and rent another pod on retry.
        features = self.api_client.get_version().get("features")
        return isinstance(features, list) and "rent_idempotency" in features

    def _cleanup_failed_resources(self, data: "LiumInstanceBackendData") -> None:
        try:
            self._cleanup_resources(data)
        except Exception:
            logger.exception(
                "Failed to delete Lium template %s or credential %s after provisioning failed. "
                "Delete them manually in Lium.",
                data.template_id,
                data.credential_id,
            )

    def _cleanup_resources(self, data: "LiumInstanceBackendData") -> None:
        if data.template_id is not None:
            self.api_client.delete_template(data.template_id)
        if data.credential_id is not None:
            self.api_client.delete_docker_credential(data.credential_id)


class LiumInstanceBackendData(CoreModel):
    pod_name: str
    executor_id: str
    startup_command: str
    template_id: Optional[str] = None
    credential_id: Optional[str] = None
    rent_payload: Optional[dict[str, Any]] = None
    idempotency_key: Optional[str] = None
    rent_started_at: Optional[datetime] = None
    rent_failed: bool = False


def _get_volume_commands(run: Run, job: Job, volumes: List[Volume]) -> list[str]:
    if not volumes:
        return []
    if len(volumes) > 1:
        raise ComputeError("Lium supports mounting only one network volume per pod")
    user = job.job_spec.user
    if user is not None and user.uid != 0 and user.username != "root":
        raise ComputeError(
            "Lium network volumes support root jobs only. "
            "Lium forces file ownership to root, so non-root jobs cannot update files."
        )
    mount_points = job.job_spec.volumes
    if mount_points is None:
        mount_points = run.run_spec.configuration.volumes
    for mount in mount_points:
        if not isinstance(mount, VolumeMountPoint):
            continue
        names = [mount.name] if isinstance(mount.name, str) else mount.name
        if volumes[0].name in names:
            path = PurePosixPath(mount.path)
            break
    else:
        raise ComputeError("Lium volume has no mount path in the job configuration")
    # Mounting over bootstrap/system directories would break SSH or the runner.
    if (
        path == PurePosixPath("/")
        or path == PurePosixPath(BOOTSTRAP_DIR)
        or path in PurePosixPath(BOOTSTRAP_DIR).parents
        or any(path.is_relative_to(p) for p in ("/proc", "/sys", "/dev"))
        or path != PurePosixPath("/mnt")
        and path.is_relative_to("/mnt")
    ):
        raise ComputeError(f"Lium volume cannot be mounted at {path}")
    commands = ["grep -q ' /mnt .* - fuse.s3fs ' /proc/self/mountinfo"]
    if str(path) != "/mnt":
        target = shlex.quote(str(path))
        commands += [f"mkdir -p -- {target}", f"mount --bind /mnt {target}"]
    return commands


def _volume_provisioning_data(volume_id: str) -> VolumeProvisioningData:
    return VolumeProvisioningData(
        backend=BackendType.LIUM,
        volume_id=volume_id,
        size_gb=None,
        # Storage and read traffic are billed by usage, not as a fixed monthly price.
        price=None,
        attachable=False,
        detachable=False,
    )


def _resource_id(resource: dict[str, Any], key: str = "id") -> str:
    value = resource.get(key)
    if not isinstance(value, str) or not value:
        raise LiumAPIError(f"Lium response has no {key}")
    return value


def _is_definitive_error(error: LiumAPIError) -> bool:
    return (
        error.status_code is not None
        and error.status_code < 500
        and error.status_code != 408
        and error.code not in {"idempotency_in_progress", "idempotency_outcome_unknown"}
    )


def _get_provider_ssh(pod: dict[str, Any]) -> SSHConnectionParams:
    # Parse connection data only; never execute the provider's SSH command.
    try:
        parts = shlex.split(pod["ssh_connect_cmd"])
        target = next(part for part in parts[1:] if "@" in part)
        user, hostname = target.rsplit("@", 1)
        port = _port(parts[parts.index("-p") + 1]) if "-p" in parts else 22
        if parts[0] != "ssh" or user != "root" or not hostname:
            raise ValueError
    except (KeyError, IndexError, StopIteration, TypeError, ValueError) as e:
        raise ProvisioningError("Lium returned invalid root SSH connection details") from e
    return SSHConnectionParams(hostname=hostname.strip("[]"), port=port, username="root")


def _port(value: Any) -> int:
    try:
        port = int(value)
        if isinstance(value, bool) or not 1 <= port <= 65535:
            raise ValueError
        return port
    except (TypeError, ValueError) as e:
        raise ProvisioningError("Lium returned an invalid SSH port") from e


def _bootstrap_runner(ssh: SSHConnectionParams, private_key: str, startup_command: str) -> None:
    with paramiko.SSHClient() as client:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=ssh.hostname,
            port=ssh.port,
            username="root",
            pkey=pkey_from_str(convert_ssh_key_to_pem(private_key)),
            timeout=SSH_TIMEOUT_SECONDS,
            banner_timeout=SSH_TIMEOUT_SECONDS,
            auth_timeout=SSH_TIMEOUT_SECONDS,
            allow_agent=False,
            look_for_keys=False,
        )
        _, stdout, _ = client.exec_command(
            _get_bootstrap_command(startup_command), timeout=SSH_TIMEOUT_SECONDS
        )
        output = stdout.read().decode().strip()
        if stdout.channel.recv_exit_status() != 0:
            raise ProvisioningError("Failed to prepare the Lium runner bootstrap")
        if output != "running":
            raise ProvisioningError("Lium runner bootstrap exited; check /root/.dstack-lium/log")


def _get_bootstrap_command(startup_command: str) -> str:
    runner_path = f"{BOOTSTRAP_DIR}/runner.sh"
    monitor_path = f"{BOOTSTRAP_DIR}/monitor.sh"
    exit_path = f"{BOOTSTRAP_DIR}/exit-code"
    # SSH replaces the image's environment and working directory. Restore both
    # from PID 1 without requiring Python in the image. Keep ENV NUL-delimited;
    # the argument count check rejects oversized environments instead of using
    # only some variables.
    # The bootstrap files stay private, but runner-created user homes and SSH
    # files must remain readable after the runner drops to the image USER.
    image_command = _get_image_env_and_cwd_command(runner_path)
    monitor = f"""umask 022
{image_command}
status=$?
printf "%s\\n" "$status" > {exit_path}
"""
    runner_script = startup_command + "\n"
    command = f"""umask 077
command -v xargs env tr wc nohup > /dev/null || exit 1
mkdir -p {BOOTSTRAP_DIR} || exit 1
if test -f {exit_path}; then
    printf exited
elif test -d {BOOTSTRAP_DIR}/started; then
    printf running
elif mkdir {BOOTSTRAP_DIR}/started 2>/dev/null; then
    printf %s {shlex.quote(runner_script)} > {runner_path} || exit 1
    printf %s {shlex.quote(monitor)} > {monitor_path} || exit 1
    nohup /bin/sh {monitor_path} > {BOOTSTRAP_DIR}/log 2>&1 < /dev/null &
    printf running
else
    printf running
fi"""
    return shlex.join(["/bin/sh", "-c", command])


def _get_image_env_and_cwd_command(runner_path: str) -> str:
    # Resolve the real directory so the non-root job does not need to traverse
    # root-only /proc/1/cwd or inherit root SSH's /root directory.
    script = f"""test "$#" -eq "$0" || exit 255
cd -P /proc/1/cwd || exit 255
exec env -i -- "$@" /bin/sh {shlex.quote(runner_path)}"""
    command = shlex.join(
        [
            "xargs",
            "-0",
            "-n",
            "2147483647",
            "/bin/sh",
            "-c",
            script,
        ]
    )
    # xargs may split large input into multiple commands. Exit 255 stops it on the
    # first partial batch, before starting a runner with only some image variables.
    return (
        "env_count=$(tr -cd '\\000' < /proc/1/environ | wc -c) &&\n"
        'test "$env_count" -gt 0 &&\n'
        f'{command} "$env_count" < /proc/1/environ'
    )
