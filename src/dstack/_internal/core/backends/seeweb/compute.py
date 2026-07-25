import shlex
from typing import List, Optional

import gpuhunt
from gpuhunt.providers.seeweb import SeewebProvider

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    ComputeWithFilteredOffersCached,
    ComputeWithInstanceVolumesSupport,
    ComputeWithMultinodeSupport,
    ComputeWithPrivilegedSupport,
    generate_unique_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.seeweb.api_client import (
    SeewebApiClient,
    SeewebPlanAvailability,
)
from dstack._internal.core.backends.seeweb.models import SeewebConfig
from dstack._internal.core.errors import BackendError, NoCapacityError, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# Seeweb auto-generates the server name; notes are limited, so keep the label short.
MAX_INSTANCE_NAME_LEN = 60

# Seeweb statuses that mean provisioning failed (matched case-insensitively).
FAILED_SERVER_STATUSES = {"failed", "error", "deleted", "deleting"}
FAILED_ACTION_STATUSES = {"failed", "error", "cancelled", "canceled"}
COMPLETED_ACTION_STATUSES = {"completed", "complete", "success", "succeeded"}

GPU_IMAGE_PREFERENCE = (
    "ubuntu-2204-uefi-nvidia-driver",
    "ubuntu-2204-nvidia-driver",
)
CPU_IMAGE_PREFERENCE = ("ubuntu-2204",)


class SeewebCompute(
    ComputeWithCreateInstanceSupport,
    ComputeWithFilteredOffersCached,
    ComputeWithPrivilegedSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithMultinodeSupport,
    Compute,
):
    def __init__(self, config: SeewebConfig):
        super().__init__()
        self.config = config
        self.api_client = SeewebApiClient(config.creds.api_token)

    def _make_catalog(self) -> gpuhunt.Catalog:
        # Seeweb pricing requires auth, so query the provider live with the project's token
        # (like the vastai/jarvislabs backends) instead of relying on the published catalog.
        catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        catalog.add_provider(SeewebProvider(token=self.config.creds.api_token))
        return catalog

    def get_offers_by_requirements(
        self, requirements: Requirements, full_offers: bool
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.SEEWEB,
            locations=self.config.regions or None,
            requirements=requirements,
            catalog=self._make_catalog(),
        )
        # A plan can be in the catalog but sold out: mark only currently-creatable
        # (plan, region) pairs as available so dstack never tries an unavailable card.
        available = self.api_client.get_available_plan_regions()
        return [
            offer.with_availability(
                availability=InstanceAvailability.AVAILABLE
                if (offer.instance.name, offer.region) in available
                else InstanceAvailability.NOT_AVAILABLE
            )
            for offer in offers
        ]

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name(
            instance_config, max_length=MAX_INSTANCE_NAME_LEN
        )
        public_keys = instance_config.get_public_keys()
        gpus = instance_offer.instance.resources.gpus
        is_gpu = len(gpus) > 0
        plan_name = instance_offer.instance.name
        availability = self.api_client.get_available_plans().get(plan_name)
        image = _select_image(
            availability=availability,
            plan_name=plan_name,
            region=instance_offer.region,
            is_gpu=is_gpu,
        )

        commands = _setup_commands(authorized_keys=public_keys, is_gpu=is_gpu)
        shim_commands = get_shim_commands(arch=instance_offer.instance.resources.cpu_arch)
        # The Seeweb GPU image reboots after its first-boot package upgrade. Do not start
        # the shim before that reboot, otherwise dstack can submit a GPU job while the
        # userspace NVIDIA libraries no longer match the still-loaded kernel module.
        commands += shim_commands[:-1]
        commands += _persist_shim_commands()
        user_customize = "#!/bin/bash\nset -euo pipefail\n" + "\n".join(commands)

        body = {
            "plan": plan_name,
            "image": image,
            "location": instance_offer.region,
            "notes": instance_name,
            "user_customize": user_customize,
        }
        # Register the project SSH key so Seeweb injects it too (the startup script also does,
        # but this covers the window before the script runs).
        if public_keys:
            body["ssh_key"] = self.api_client.get_or_create_ssh_key(public_keys[0])

        server, action_id = self.api_client.create_server(body)

        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=server["name"],
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="root",
            ssh_port=22,
            ssh_proxy=None,
            dockerized=True,
            backend_data=SeewebInstanceBackendData(action_id=action_id).json(),
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        backend_data = SeewebInstanceBackendData.load(provisioning_data.backend_data)
        action_completed = backend_data.action_id is None
        if backend_data.action_id is not None:
            action = self.api_client.get_action(backend_data.action_id)
            if action is None:
                return
            action_status = str(action.get("status") or "").lower()
            if action_status in FAILED_ACTION_STATUSES:
                raise ProvisioningError(
                    f"Seeweb action {backend_data.action_id} entered status {action_status!r}"
                )
            action_completed = action_status in COMPLETED_ACTION_STATUSES
            if not action_completed:
                return

        server = self.api_client.get_server(provisioning_data.instance_id)
        if server is None:
            # The server endpoint can lag briefly after the creation action completes.
            return
        status = (server.get("status") or "").lower()
        if status in FAILED_SERVER_STATUSES:
            raise ProvisioningError(
                f"Seeweb server {provisioning_data.instance_id} entered status {status!r}"
            )
        ipv4 = server.get("ipv4")
        if action_completed and isinstance(ipv4, str) and ipv4:
            provisioning_data.hostname = ipv4

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        self.api_client.delete_server(instance_id)


def _select_image(
    *,
    availability: Optional[SeewebPlanAvailability],
    plan_name: str,
    region: str,
    is_gpu: bool,
) -> str:
    """Choose an image actually allowed by the plan, preferring the NVIDIA UEFI image."""
    if availability is None or region not in availability.regions:
        raise NoCapacityError(f"Seeweb plan {plan_name} is not available in region {region}")
    preference = GPU_IMAGE_PREFERENCE if is_gpu else CPU_IMAGE_PREFERENCE
    for image in preference:
        if image in availability.images:
            return image
    workload = "GPU" if is_gpu else "CPU"
    raise BackendError(
        f"Seeweb plan {plan_name} has no supported {workload} image in region {region}"
    )


def _setup_commands(authorized_keys: List[str], is_gpu: bool) -> List[str]:
    key_commands = []
    for key in dict.fromkeys(key.strip() for key in authorized_keys if key.strip()):
        key_commands.append(f"printf '%s\\n' {shlex.quote(key)} >> /root/.ssh/authorized_keys")
    commands = [
        "install -d -m 0700 /root/.ssh",
        "touch /root/.ssh/authorized_keys",
        "chmod 0600 /root/.ssh/authorized_keys",
        *key_commands,
        "export DEBIAN_FRONTEND=noninteractive",
    ]
    commands += _install_docker_commands()
    if is_gpu:
        commands += _install_nvidia_container_toolkit_commands()
    return commands


def _install_docker_commands() -> List[str]:
    return [
        "install -d -m 0755 /etc/apt/keyrings",
        "curl --max-time 60 -fsSL https://download.docker.com/linux/ubuntu/gpg"
        " | gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg",
        "chmod a+r /etc/apt/keyrings/docker.gpg",
        'echo "deb [arch=$(dpkg --print-architecture)'
        " signed-by=/etc/apt/keyrings/docker.gpg]"
        ' https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"'
        " | tee /etc/apt/sources.list.d/docker.list > /dev/null",
        "apt-get update",
        "apt-get --assume-yes install docker-ce docker-ce-cli containerd.io"
        " docker-compose-plugin jq",
        "systemctl enable --now docker.service",
    ]


def _install_nvidia_container_toolkit_commands() -> List[str]:
    return [
        "apt-get --assume-yes install nvidia-container-toolkit",
        "nvidia-ctk runtime configure --runtime=docker",
        # `systemctl restart` can report non-zero under the Seeweb cloud-init runner even when
        # Docker comes up fine; keep it non-fatal so the chained runner/shim commands still run.
        "systemctl restart docker.service || true",
    ]


def _persist_shim_commands() -> List[str]:
    """Make the shim survive the reboot performed by Seeweb's GPU image updates."""
    unit_lines = [
        "[Unit]",
        "Description=dstack shim",
        "Wants=network-online.target",
        "After=network-online.target docker.service",
        "",
        "[Service]",
        "EnvironmentFile=/etc/dstack-shim.env",
        "ExecStart=/usr/local/bin/dstack-shim",
        "Restart=always",
        "RestartSec=3",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
    ]
    write_unit = "printf '%s\\n' " + " ".join(map(shlex.quote, unit_lines))
    return [
        "env | grep '^DSTACK_' > /etc/dstack-shim.env",
        "chmod 0600 /etc/dstack-shim.env",
        f"{write_unit} > /etc/systemd/system/dstack-shim.service",
        "systemctl daemon-reload",
        # Do not start the service on the initial boot. Seeweb's GPU image performs an
        # automatic reboot after cloud-init, and the service must become reachable only then.
        "systemctl enable dstack-shim.service",
    ]


class SeewebInstanceBackendData(CoreModel):
    action_id: Optional[int] = None

    @classmethod
    def load(cls, raw: Optional[str]) -> "SeewebInstanceBackendData":
        if raw is None:
            return cls()
        return cls.__response__.parse_raw(raw)
