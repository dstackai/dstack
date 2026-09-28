import re
import shlex
import time
from typing import Any, List, Optional

import gpuhunt
from gpuhunt.providers.daytona import DaytonaProvider

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
from dstack._internal.core.backends.daytona.api_client import DaytonaAPIClient, DaytonaAPIError
from dstack._internal.core.backends.daytona.models import DaytonaConfig
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ComputeError, NotYetTerminated, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel, RegistryAuth, validate_json_extra_ignore
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    SSHConnectionParams,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import (
    DaytonaVolumeConfiguration,
    Volume,
    VolumeMountPoint,
    VolumeProvisioningData,
)
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.docker import DEFAULT_REGISTRY, is_default_registry, parse_image_name
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

MAX_INSTANCE_NAME_LEN = 63
RUNNER_SESSION = "dstack-runner"
# A replacement token revokes the previous one for new connections. Request one
# ten-year credential at provisioning and reuse it for the sandbox's lifetime.
SSH_ACCESS_MINUTES = 3650 * 24 * 60
VOLUME_READY_TIMEOUT = 60


class DaytonaCompute(ComputeWithFilteredOffersCached, ComputeWithVolumeSupport, Compute):
    def __init__(self, config: DaytonaConfig):
        super().__init__()
        self.config = config
        self.api_client = DaytonaAPIClient(config.creds.api_key)
        self._catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self._catalog.add_provider(DaytonaProvider(api_key=config.creds.api_key))
        self._organization_id: Optional[str] = None

    def get_offers_by_requirements(
        self, requirements: Requirements, full_offers: bool, unallocated_resources: bool
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.DAYTONA,
            locations=self.config.regions or None,
            requirements=requirements,
            catalog=self._catalog,
        )
        if not offers:
            return []
        organization_id = self._organization_id
        if organization_id is None:
            organization_id = self.api_client.get_current_api_key().get("organizationId")
            if not isinstance(organization_id, str) or not organization_id:
                raise DaytonaAPIError("Daytona API key has no organization")
            self._organization_id = organization_id
        usage = self.api_client.get_organization_usage(organization_id)
        classes = self.api_client.get_available_sandbox_classes(organization_id)
        region_usage = {
            row["regionId"]: row
            for row in usage["regionUsage"]
            if row["sandboxClass"] == "container"
        }
        region_classes = {
            row["regionId"]: row for row in classes if row["sandboxClass"] == "container"
        }
        return [
            offer.with_availability(
                availability=(
                    InstanceAvailability.AVAILABLE
                    if _has_quota(
                        offer,
                        region_usage.get(offer.region),
                        region_classes.get(offer.region),
                    )
                    else InstanceAvailability.NO_QUOTA
                ),
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
        # Whitespace could inject additional Dockerfile instructions.
        if not image_name or re.search(r"\s", image_name):
            raise ComputeError("Invalid Daytona container image name")
        instance_name = generate_unique_instance_name_for_job(
            run, job, max_length=MAX_INSTANCE_NAME_LEN
        )
        commands = get_docker_commands(
            build_authorized_keys(project_ssh_public_key, extra_authorized_keys)
        )
        backend_data = DaytonaInstanceBackendData(
            startup_command=shlex.join(["sh", "-c", " && ".join(commands)])
        )
        registry: Optional[str] = None
        if job.job_spec.registry_auth is not None:
            image = parse_image_name(image_name)
            registry = image.registry or DEFAULT_REGISTRY
            if is_default_registry(registry):
                registry = DEFAULT_REGISTRY
            # Daytona's Dockerfile builder includes organization credentials only
            # for FROM images with a registry prefix.
            suffix = f"@{image.digest}" if image.digest else f":{image.tag}"
            image_name = f"{registry}/{image.repo}{suffix}"
        resources = instance_offer.instance.resources
        payload = {
            "name": instance_name,
            "buildInfo": {
                # The sandbox's user field does not override the image USER.
                # Daytona caches builds, so updating a mutable tag such as latest may
                # still reuse an older image. A digest-pinned image avoids this.
                "dockerfileContent": (
                    f'FROM {image_name}\nUSER root\nENTRYPOINT []\nCMD ["sleep", "infinity"]\n'
                )
            },
            "user": "root",
            "target": instance_offer.region,
            "cpu": resources.cpus,
            "memory": round(resources.memory_mib / 1024),
            "disk": round(resources.disk.size_mib / 1024),
            "gpu": len(resources.gpus),
            "spot": resources.spot,
            "public": False,
            "autoStopInterval": 0,
            "autoPauseInterval": 0,
            "autoDeleteInterval": 0,
            "ttlMinutes": 0,
        }
        if resources.gpus:
            payload["gpuType"] = [_get_gpu_type(instance_offer)]
        if volumes:
            mount_points = job.job_spec.volumes
            if mount_points is None:
                mount_points = run.run_spec.configuration.volumes
            paths = {}
            for mount in mount_points:
                if isinstance(mount, VolumeMountPoint):
                    names = [mount.name] if isinstance(mount.name, str) else mount.name
                    paths.update((name, mount.path) for name in names)
            payload["volumes"] = [
                {"volumeId": get_or_error(volume.volume_id), "mountPath": paths[volume.name]}
                for volume in volumes
            ]
        if job.job_spec.registry_auth is not None:
            # Daytona selects registry credentials at organization scope, without a
            # per-sandbox selector. Another record for the same registry can affect this pull.
            backend_data.registry_id = self._create_registry(
                f"{instance_name}-registry", get_or_error(registry), job.job_spec.registry_auth
            )
        instance_id = instance_name
        try:
            sandbox = self.api_client.create_sandbox(payload)
            if isinstance(sandbox.get("id"), str) and sandbox["id"]:
                instance_id = sandbox["id"]
        except DaytonaAPIError as e:
            if e.status_code is not None and e.status_code < 500:
                self._cleanup_failed_registry(backend_data.registry_id)
                raise
            # A timed-out create may have succeeded. Persist its unique name so
            # provisioning can find it and termination can clean it up; never retry POST.
            logger.warning(
                "Daytona sandbox %s creation response was lost; checking by name", instance_name
            )
        except Exception:
            self._cleanup_failed_registry(backend_data.registry_id)
            raise
        return JobProvisioningData(
            backend=BackendType.DAYTONA,
            instance_type=instance_offer.instance,
            instance_id=instance_id,
            region=instance_offer.region,
            price=instance_offer.price,
            username="root",
            dockerized=False,
            backend_data=backend_data.model_dump_json(),
        )

    def _create_registry(self, name: str, url: str, auth: RegistryAuth) -> str:
        try:
            registry = self.api_client.create_registry(
                {"name": name, "url": url, "username": auth.username, "password": auth.password}
            )
            return registry["id"]
        except DaytonaAPIError as e:
            if e.status_code is not None and e.status_code < 500:
                raise
            # Recover the exact per-job record if its create response was lost.
            for registry in self.api_client.get_registries():
                if registry["name"] == name:
                    return registry["id"]
            raise

    def _cleanup_failed_registry(self, registry_id: Optional[str]) -> None:
        if registry_id is None:
            return
        try:
            self.api_client.delete_registry(registry_id)
        except Exception:
            logger.exception(
                "Failed to delete Daytona registry %s after provisioning failed. "
                "Delete it manually in Daytona.",
                registry_id,
            )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        if provisioning_data.hostname is not None and provisioning_data.ssh_port is not None:
            return
        sandbox = self.api_client.get_sandbox(provisioning_data.instance_id)
        if sandbox is None:
            # The create response may have been lost before the sandbox became visible.
            # The server's provisioning timeout still schedules deletion by name.
            return
        state = sandbox.get("state")
        if state in {
            "error",
            "build_failed",
            "destroyed",
            "destroying",
            "stopped",
            "stopping",
            "archived",
            "archiving",
            "paused",
            "pausing",
        }:
            reason = sandbox.get("errorReason") or state
            raise ProvisioningError(f"Daytona sandbox failed to start: {reason}")
        if state != "started":
            return
        backend_data = validate_json_extra_ignore(
            DaytonaInstanceBackendData, provisioning_data.backend_data or "{}"
        )
        toolbox_url = self.api_client.get_toolbox_url(sandbox["id"])
        self._start_runner(toolbox_url, get_or_error(backend_data.startup_command))
        access = self.api_client.create_ssh_access(
            sandbox["id"], expires_in_minutes=SSH_ACCESS_MINUTES
        )
        provisioning_data.ssh_proxy = _get_ssh_proxy(access)
        provisioning_data.hostname = "localhost"
        provisioning_data.ssh_port = DSTACK_RUNNER_SSH_PORT
        # The server checks runner readiness through the normal SSH connection.
        backend_data.startup_command = None
        provisioning_data.backend_data = (
            backend_data.model_dump_json() if backend_data.registry_id is not None else None
        )

    def _start_runner(self, toolbox_url: str, startup_command: str) -> None:
        session = self.api_client.get_session(toolbox_url, RUNNER_SESSION)
        if session is None:
            self.api_client.create_session(toolbox_url, RUNNER_SESSION)
            session = {"commands": []}
        commands = session["commands"]
        if not commands:
            self.api_client.execute_session_command(
                toolbox_url, RUNNER_SESSION, startup_command, run_async=True
            )
            return
        for command in commands:
            if command.get("exitCode") is not None:
                raise ProvisioningError(
                    "Daytona runner setup exited with code "
                    f"{command['exitCode']}. Check the dstack-runner session in Daytona."
                )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        sandbox = self.api_client.get_sandbox(instance_id)
        if sandbox is not None and sandbox.get("state") != "destroyed":
            if sandbox.get("state") != "destroying":
                self.api_client.delete_sandbox(instance_id)
            raise NotYetTerminated("Waiting for Daytona sandbox deletion")
        data = validate_json_extra_ignore(DaytonaInstanceBackendData, backend_data or "{}")
        if data.registry_id is not None:
            self.api_client.delete_registry(data.registry_id)

    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        assert isinstance(volume.configuration, DaytonaVolumeConfiguration)
        volume_id = get_or_error(volume.configuration.volume_id)
        self._wait_for_volume(volume_id)
        return _volume_provisioning_data(volume_id)

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        name = generate_unique_volume_name(volume)
        try:
            data = self.api_client.create_volume(name)
        except DaytonaAPIError as e:
            if e.status_code is not None and e.status_code < 500:
                raise
            data = self.api_client.get_volume_by_name(name)
            if data is None:
                raise
        volume_id = data["id"]
        try:
            self._wait_for_volume(volume_id)
        except Exception:
            try:
                self.api_client.delete_volume(volume_id)
            except Exception:
                logger.exception(
                    "Failed to delete Daytona volume %s after provisioning failed. "
                    "Delete it manually in Daytona.",
                    volume_id,
                )
            raise
        return _volume_provisioning_data(volume_id)

    def _wait_for_volume(self, volume_id: str) -> None:
        deadline = time.monotonic() + VOLUME_READY_TIMEOUT
        while True:
            data = self.api_client.get_volume(volume_id)
            if data is None:
                raise ComputeError(f"Daytona volume {volume_id} not found")
            state = data["state"]
            if state == "ready":
                return
            if state not in {"pending_create", "creating"}:
                raise ComputeError(
                    f"Daytona volume {volume_id} is {state}: {data.get('errorReason') or state}"
                )
            if time.monotonic() >= deadline:
                raise ComputeError(f"Timed out waiting for Daytona volume {volume_id}")
            time.sleep(2)

    def delete_volume(self, volume: Volume) -> None:
        if volume.volume_id is None:
            return
        data = self.api_client.get_volume(volume.volume_id)
        if data is None or data["state"] in {"pending_delete", "deleting", "deleted"}:
            return
        self.api_client.delete_volume(volume.volume_id)


class DaytonaInstanceBackendData(CoreModel):
    startup_command: Optional[str] = None
    registry_id: Optional[str] = None


def _volume_provisioning_data(volume_id: str) -> VolumeProvisioningData:
    return VolumeProvisioningData(
        backend=BackendType.DAYTONA,
        volume_id=volume_id,
        size_gb=None,
        price=0,
        attachable=False,
        detachable=False,
    )


def _has_quota(
    offer: InstanceOffer,
    usage: Optional[dict[str, Any]],
    sandbox_class: Optional[dict[str, Any]],
) -> bool:
    if usage is None or sandbox_class is None:
        return False
    resources = offer.instance.resources
    sizes = {
        "Cpu": resources.cpus,
        "Memory": resources.memory_mib / 1024,
        "Disk": resources.disk.size_mib / 1024,
    }
    gpu_count = len(resources.gpus)
    if gpu_count:
        if not sandbox_class.get("gpuAvailable"):
            return False
        if not resources.spot and gpu_count > usage["totalGpuQuota"] - usage["currentGpuUsage"]:
            return False
        for limits in (usage, sandbox_class):
            allowed_types = limits.get("allowedGpuTypes")
            if allowed_types is not None and _get_gpu_type(offer) not in allowed_types:
                return False
        # GPU sandboxes use separate quotas: CPU/RAM/disk aggregate totals may be zero.
        # Check per-GPU limits, falling back to per-sandbox limits.
        for name, size in sizes.items():
            limit = usage.get(f"max{name}PerGpu")
            if limit is not None:
                limit *= gpu_count
            else:
                limit = usage.get(f"max{name}PerSandbox")
            if limit is not None and size > limit:
                return False
        return True
    for name, size in sizes.items():
        if size > usage[f"total{name}Quota"] - usage[f"current{name}Usage"]:
            return False
        limit = usage.get(f"max{name}PerSandbox")
        if limit is not None and size > limit:
            return False
    return True


def _get_gpu_type(offer: InstanceOffer) -> str:
    return offer.backend_data.get("gpu_type") or offer.instance.resources.gpus[0].name


def _get_ssh_proxy(access: dict[str, Any]) -> SSHConnectionParams:
    # Parse only the endpoint; never execute the provider's command or log its token.
    try:
        parts = shlex.split(access["sshCommand"])
        target = next(part for part in parts[1:] if "@" in part)
        _, hostname = target.rsplit("@", 1)
        port = int(parts[parts.index("-p") + 1]) if "-p" in parts else 22
        if parts[0] != "ssh" or not hostname or not access["token"] or not 1 <= port <= 65535:
            raise ValueError
    except (KeyError, IndexError, StopIteration, TypeError, ValueError) as e:
        raise ProvisioningError("Daytona returned invalid SSH connection details") from e
    return SSHConnectionParams(hostname=hostname, port=port, username=access["token"])
