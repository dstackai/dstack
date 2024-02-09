import hashlib
import subprocess
import tempfile
import time
from threading import Thread
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from dstack._internal.core.backends.base.compute import (
    Compute,
    get_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.lambdalabs.api_client import LambdaAPIClient
from dstack._internal.core.backends.lambdalabs.config import LambdaConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run

_SHIM_CONFIG_FILEPATH = "/home/ubuntu/.dstack/config.json"


class _ShimConfig(BaseModel):
    instance_id: str
    api_key: str


class LambdaCompute(Compute):
    def __init__(self, config: LambdaConfig):
        self.config = config
        self.api_client = LambdaAPIClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.LAMBDA,
            locations=self.config.regions,
            requirements=requirements,
        )
        offers_with_availability = self._get_offers_with_availability(offers)
        return offers_with_availability

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        commands = get_shim_commands(
            backend=BackendType.LAMBDA,
            image_name=job.job_spec.image_name,
            authorized_keys=[
                run.run_spec.ssh_key_pub.strip(),
                project_ssh_public_key.strip(),
            ],
            registry_auth_required=job.job_spec.registry_auth is not None,
        )
        # shim is asssumed to be run under root
        launch_command = "sudo sh -c '" + "&& ".join(commands) + "'"
        return _run_instance(
            api_client=self.api_client,
            region=instance_offer.region,
            instance_type_name=instance_offer.instance.name,
            user_ssh_public_key=run.run_spec.ssh_key_pub,
            project_ssh_public_key=project_ssh_public_key,
            project_ssh_private_key=project_ssh_private_key,
            instance_name=get_instance_name(run, job),
            launch_command=launch_command,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        self.api_client.terminate_instances(instance_ids=[instance_id])

    def _get_offers_with_availability(
        self, offers: List[InstanceOffer]
    ) -> List[InstanceOfferWithAvailability]:
        instance_availability = {
            instance_name: [
                region["name"] for region in details["regions_with_capacity_available"]
            ]
            for instance_name, details in self.api_client.list_instance_types().items()
        }
        availability_offers = []
        for offer in offers:
            if offer.region not in self.config.regions:
                continue
            availability = InstanceAvailability.NOT_AVAILABLE
            if offer.region in instance_availability.get(offer.instance.name, []):
                availability = InstanceAvailability.AVAILABLE
            availability_offers.append(
                InstanceOfferWithAvailability(**offer.dict(), availability=availability)
            )
        return availability_offers


def _run_instance(
    api_client: LambdaAPIClient,
    region: str,
    instance_type_name: str,
    user_ssh_public_key: str,
    project_ssh_public_key: str,
    project_ssh_private_key: str,
    instance_name: str,
    launch_command: str,
) -> LaunchedInstanceInfo:
    _, project_key_name = _add_ssh_keys(
        api_client=api_client,
        user_ssh_public_key=user_ssh_public_key,
        project_ssh_public_key=project_ssh_public_key,
    )
    instances_ids = api_client.launch_instances(
        region_name=region,
        instance_type_name=instance_type_name,
        ssh_key_names=[project_key_name],
        name=instance_name,
        quantity=1,
        file_system_names=[],
    )
    instance_id = instances_ids[0]
    instance_info = _wait_for_instance(api_client, instance_id)
    thread = Thread(
        target=_start_runner,
        kwargs={
            "hostname": instance_info["ip"],
            "project_ssh_private_key": project_ssh_private_key,
            "user_ssh_public_key": user_ssh_public_key,
            "config": _ShimConfig(instance_id=instance_id, api_key=api_client.api_key),
            "launch_command": launch_command,
        },
        daemon=True,
    )
    thread.start()
    return LaunchedInstanceInfo(
        instance_id=instance_id,
        ip_address=instance_info["ip"],
        region=region,
        username="ubuntu",
        ssh_port=22,
        dockerized=True,
        ssh_proxy=None,
        backend_data=None,
    )


def _add_ssh_keys(
    api_client: LambdaAPIClient, user_ssh_public_key: str, project_ssh_public_key: str
) -> Tuple[str, str]:
    ssh_keys = api_client.list_ssh_keys()
    ssh_key_names: List[str] = [k["name"] for k in ssh_keys]
    user_key_name = _add_ssh_key(api_client, ssh_key_names, user_ssh_public_key)
    project_key_name = _add_ssh_key(api_client, ssh_key_names, project_ssh_public_key)
    return user_key_name, project_key_name


def _add_ssh_key(api_client: LambdaAPIClient, ssh_key_names: List[str], public_key: str) -> str:
    key_name = _get_ssh_key_name(public_key)
    if key_name in ssh_key_names:
        return key_name
    api_client.add_ssh_key(name=key_name, public_key=public_key)
    return key_name


def _get_ssh_key_name(public_key: str) -> str:
    return hashlib.sha1(public_key.encode()).hexdigest()[-16:]


_WAIT_FOR_INSTANCE_ATTEMPTS = 60
_WAIT_FOR_INSTANCE_INTERVAL = 10


def _wait_for_instance(
    api_client: LambdaAPIClient,
    instance_id: str,
) -> Dict:
    for _ in range(_WAIT_FOR_INSTANCE_ATTEMPTS):
        instance_info = _get_instance_info(api_client, instance_id)
        if instance_info is None or instance_info["status"] != "booting":
            return instance_info
        time.sleep(_WAIT_FOR_INSTANCE_INTERVAL)


def _get_instance_info(api_client: LambdaAPIClient, instance_id: str) -> Optional[Dict]:
    instances = api_client.list_instances()
    instance_id_to_instance_map = {i["id"]: i for i in instances}
    instance = instance_id_to_instance_map.get(instance_id)
    if instance is None:
        return None
    return instance


def _start_runner(
    hostname: str,
    project_ssh_private_key: str,
    user_ssh_public_key: str,
    config: _ShimConfig,
    launch_command: str,
):
    _setup_instance(
        hostname=hostname,
        ssh_private_key=project_ssh_private_key,
        user_ssh_public_key=user_ssh_public_key,
    )
    _launch_runner(
        hostname=hostname,
        ssh_private_key=project_ssh_private_key,
        config=config,
        launch_command=launch_command,
    )


def _setup_instance(
    hostname: str,
    ssh_private_key: str,
    user_ssh_public_key: str,
):
    # Lambda API allows specifying only one ssh key,
    # so we have to update authorized_keys manually to add the user key
    setup_commands = (
        f"echo '{user_ssh_public_key}' >> /home/ubuntu/.ssh/authorized_keys && "
        "mkdir /home/ubuntu/.dstack && "
        "sudo apt-get update && "
        "sudo apt-get install -y --no-install-recommends nvidia-docker2 && "
        "sudo pkill -SIGHUP dockerd"
    )
    _run_ssh_command(hostname=hostname, ssh_private_key=ssh_private_key, command=setup_commands)


def _launch_runner(
    hostname: str,
    ssh_private_key: str,
    config: _ShimConfig,
    launch_command: str,
):
    _upload_config(
        hostname=hostname,
        ssh_private_key=ssh_private_key,
        config=config,
    )
    _run_ssh_command(
        hostname=hostname,
        ssh_private_key=ssh_private_key,
        command=launch_command,
    )


def _upload_config(
    hostname: str,
    ssh_private_key: str,
    config: _ShimConfig,
):
    with tempfile.NamedTemporaryFile("w+", 0o600) as f:
        f.write(config.json())
        f.flush()
        _run_scp_command(
            hostname=hostname,
            ssh_private_key=ssh_private_key,
            source=f.name,
            target=_SHIM_CONFIG_FILEPATH,
        )


def _run_ssh_command(hostname: str, ssh_private_key: str, command: str):
    with tempfile.NamedTemporaryFile("w+", 0o600) as f:
        f.write(ssh_private_key)
        f.flush()
        subprocess.run(
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-i",
                f.name,
                f"ubuntu@{hostname}",
                command,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _run_scp_command(hostname: str, ssh_private_key: str, source: str, target: str):
    with tempfile.NamedTemporaryFile("w+", 0o600) as f:
        f.write(ssh_private_key)
        f.flush()
        subprocess.run(
            [
                "scp",
                "-o",
                "StrictHostKeyChecking=no",
                "-i",
                f.name,
                source,
                f"ubuntu@{hostname}:{target}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
