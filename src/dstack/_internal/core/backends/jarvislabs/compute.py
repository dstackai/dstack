import shlex
import subprocess
import tempfile
from collections.abc import Iterable
from typing import List, Optional, cast

import gpuhunt
from gpuhunt.providers.jarvislabs import JarvisLabsProvider
from typing_extensions import NotRequired, TypedDict

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithPrivilegedSupport,
    generate_unique_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import (
    OfferModifier,
    get_catalog_offers,
    get_offers_disk_modifier,
)
from dstack._internal.core.backends.jarvislabs.api_client import JarvisLabsAPIClient
from dstack._internal.core.backends.jarvislabs.models import JarvisLabsConfig
from dstack._internal.core.errors import ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.resources import Memory, Range
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

MAX_INSTANCE_NAME_LEN = 40
# JarvisLabs VM storage is configurable through the `hdd` create parameter.
MIN_DISK_SIZE = Memory.parse("100GB")
CONFIGURABLE_DISK_SIZE = Range[Memory](min=MIN_DISK_SIZE, max=None)
DEFAULT_USERNAME = "ubuntu"
SSH_CONNECT_TIMEOUT_SECONDS = 10
SSH_SETUP_TIMEOUT_SECONDS = 240
SSH_LAUNCH_TIMEOUT_SECONDS = 60


class JarvisLabsOfferBackendData(TypedDict):
    # Set by gpuhunt when normalized GPU identity differs from the JarvisLabs VM
    # create token, e.g. "RTX-PRO6000" normalized to "RTXPRO6000".
    gpu_type: NotRequired[str]


class JarvisLabsInstanceBackendData(CoreModel):
    ssh_key_ids: Optional[List[str]] = None

    @classmethod
    def load(cls, raw: Optional[str]) -> "JarvisLabsInstanceBackendData":
        if raw is None:
            return cls()
        return cls.__response__.parse_raw(raw)


class JarvisLabsCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithInstanceVolumesSupport,
    Compute,
):
    def __init__(self, config: JarvisLabsConfig):
        super().__init__()
        self.config = config
        self.api_client = JarvisLabsAPIClient(config.creds.api_key)
        self._catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self._catalog.add_provider(JarvisLabsProvider(api_key=self.config.creds.api_key))

    def get_all_offers_with_availability(self) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.JARVISLABS,
            locations=self.config.regions or None,
            catalog=self._catalog,
            configurable_disk_size=CONFIGURABLE_DISK_SIZE,
        )
        return [
            offer.with_availability(availability=InstanceAvailability.AVAILABLE)
            for offer in offers
        ]

    def get_offers_modifiers(self, requirements: Requirements) -> Iterable[OfferModifier]:
        return [get_offers_disk_modifier(CONFIGURABLE_DISK_SIZE, requirements)]

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name(
            instance_config, max_length=MAX_INSTANCE_NAME_LEN
        )
        ssh_key_ids: List[str] = []
        instance_id = None
        try:
            for idx, ssh_public_key in enumerate(instance_config.get_public_keys()):
                ssh_key_ids.append(
                    _create_ssh_key(
                        client=self.api_client,
                        name=f"{instance_name}-{idx}.key",
                        public_key=ssh_public_key,
                    )
                )
            if instance_offer.instance.resources.gpus:
                instance_id = self.api_client.create_gpu_vm(
                    gpu_type=_get_jarvislabs_gpu_type(instance_offer),
                    num_gpus=len(instance_offer.instance.resources.gpus),
                    is_spot=instance_offer.instance.resources.spot,
                    storage=_get_disk_size_gb(instance_offer),
                    region=instance_offer.region,
                    name=instance_name,
                )
            else:
                instance_id = self.api_client.create_cpu_vm(
                    vcpus=instance_offer.instance.resources.cpus,
                    ram_gb=round(instance_offer.instance.resources.memory_mib / 1024),
                    storage=_get_disk_size_gb(instance_offer),
                    region=instance_offer.region,
                    name=instance_name,
                )

        except BaseException:
            if instance_id is not None:
                try:
                    self.api_client.destroy_instance(
                        machine_id=instance_id,
                        region=instance_offer.region,
                    )
                except Exception:
                    logger.exception(
                        "Could not destroy failed JarvisLabs instance %s", instance_id
                    )
            try:
                _delete_ssh_keys(self.api_client, ssh_key_ids)
            except Exception:
                logger.exception(
                    "Could not delete JarvisLabs SSH keys %s after provisioning failure",
                    ssh_key_ids,
                )
            raise
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_id,
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username=DEFAULT_USERNAME,
            ssh_port=22,
            dockerized=True,
            ssh_proxy=None,
            backend_data=JarvisLabsInstanceBackendData(ssh_key_ids=ssh_key_ids).json(),
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        instance = self.api_client.get_instance(provisioning_data.instance_id)
        if instance is None:
            status = self.api_client.get_instance_status(
                machine_id=provisioning_data.instance_id,
                region=provisioning_data.region,
            )
            if status is not None and str(status.get("status")).lower() == "failed":
                _raise_failed_status(status)
            return

        status = str(instance.get("status")).lower()
        if status == "failed":
            _raise_failed_status(instance)
        if status != "running":
            return

        hostname = instance.get("public_ip")
        if not hostname:
            return
        username = _get_ssh_username(instance)
        if not _start_runner(
            hostname=hostname,
            username=username,
            project_ssh_private_key=project_ssh_private_key,
            arch=provisioning_data.instance_type.resources.cpu_arch,
        ):
            return
        provisioning_data.hostname = hostname
        provisioning_data.username = username

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        backend_data_parsed = JarvisLabsInstanceBackendData.load(backend_data)
        self.api_client.destroy_instance(machine_id=instance_id, region=region)
        _delete_ssh_keys(self.api_client, backend_data_parsed.ssh_key_ids)


def _create_ssh_key(client: JarvisLabsAPIClient, name: str, public_key: str) -> str:
    return client.create_ssh_key(public_key=public_key, key_name=name)


def _delete_ssh_keys(client: JarvisLabsAPIClient, ssh_key_ids: Optional[List[str]]) -> None:
    if not ssh_key_ids:
        return
    for ssh_key_id in ssh_key_ids:
        client.delete_ssh_key(ssh_key_id)


def _get_jarvislabs_gpu_type(instance_offer: InstanceOfferWithAvailability) -> str:
    gpu_type = _get_jarvislabs_gpu_type_from_backend_data(instance_offer.backend_data)
    if gpu_type is not None:
        return gpu_type

    gpu = instance_offer.instance.resources.gpus[0]
    return gpu.name


def _get_jarvislabs_gpu_type_from_backend_data(backend_data: dict) -> Optional[str]:
    offer_backend_data = cast(JarvisLabsOfferBackendData, backend_data)
    gpu_type = offer_backend_data.get("gpu_type")
    if not isinstance(gpu_type, str) or not gpu_type:
        return None
    return gpu_type


def _get_disk_size_gb(instance_offer: InstanceOfferWithAvailability) -> int:
    disk_size_gb = round(instance_offer.instance.resources.disk.size_mib / 1024)
    return max(round(MIN_DISK_SIZE), disk_size_gb)


def _format_failed_status(status: dict) -> str:
    message = status.get("error") or "unknown error"
    code = status.get("code")
    if code is not None:
        return f"JarvisLabs instance creation failed: {message} (code={code})"
    return f"JarvisLabs instance creation failed: {message}"


def _raise_failed_status(status: dict) -> None:
    raise ProvisioningError(_format_failed_status(status), status)


def _get_ssh_username(instance: dict) -> str:
    ssh_command = instance.get("ssh_str") or instance.get("ssh_command")
    if not isinstance(ssh_command, str):
        return DEFAULT_USERNAME
    try:
        parts = shlex.split(ssh_command)
    except ValueError:
        return DEFAULT_USERNAME
    for part in parts[1:]:
        if part.startswith("-") or "@" not in part:
            continue
        return part.rsplit("@", 1)[0]
    return DEFAULT_USERNAME


def _start_runner(
    hostname: str,
    username: str,
    project_ssh_private_key: str,
    arch: Optional[str],
) -> bool:
    commands = get_shim_commands(arch=arch)
    launch_command = "sudo sh -c " + shlex.quote(" && ".join(commands))
    try:
        if not _setup_instance(
            hostname=hostname,
            username=username,
            ssh_private_key=project_ssh_private_key,
        ):
            return False
        return _launch_runner(
            hostname=hostname,
            username=username,
            ssh_private_key=project_ssh_private_key,
            launch_command=launch_command,
        )
    except Exception:
        logger.exception("Failed to start dstack shim on JarvisLabs instance %s", hostname)
        return False


def _setup_instance(
    hostname: str,
    username: str,
    ssh_private_key: str,
) -> bool:
    setup_commands = [
        "mkdir -p ~/.dstack",
        "if ! command -v curl >/dev/null 2>&1 || ! command -v docker >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then sudo apt-get update; fi",
        "if ! command -v curl >/dev/null 2>&1; then sudo DEBIAN_FRONTEND=noninteractive apt-get install -y curl; fi",
        "if ! command -v docker >/dev/null 2>&1; then sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io; fi",
        "if ! command -v jq >/dev/null 2>&1; then sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y jq; fi",
        "sudo systemctl enable --now docker || sudo service docker start || true",
    ]
    return _run_ssh_command(
        hostname=hostname,
        username=username,
        ssh_private_key=ssh_private_key,
        command=" && ".join(setup_commands),
        timeout=SSH_SETUP_TIMEOUT_SECONDS,
    )


def _launch_runner(
    hostname: str,
    username: str,
    ssh_private_key: str,
    launch_command: str,
) -> bool:
    daemonized_command = f"{launch_command.rstrip('&')} >/tmp/dstack-shim.log 2>&1 & disown"
    return _run_ssh_command(
        hostname=hostname,
        username=username,
        ssh_private_key=ssh_private_key,
        command=daemonized_command,
        timeout=SSH_LAUNCH_TIMEOUT_SECONDS,
    )


def _run_ssh_command(
    hostname: str,
    username: str,
    ssh_private_key: str,
    command: str,
    timeout: int,
) -> bool:
    with tempfile.NamedTemporaryFile("w+") as f:
        f.write(ssh_private_key)
        f.flush()
        try:
            proc = subprocess.run(
                [
                    "ssh",
                    "-F",
                    "none",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                    "-o",
                    "ConnectionAttempts=1",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "LogLevel=ERROR",
                    "-i",
                    f.name,
                    f"{username}@{hostname}",
                    command,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            logger.debug("Timed out running SSH command on JarvisLabs instance %s", hostname)
            return False
        if proc.returncode != 0:
            logger.debug(
                "SSH command failed on JarvisLabs instance %s: exit_code=%s stderr=%r",
                hostname,
                proc.returncode,
                proc.stderr[-1000:],
            )
            return False
        return True
