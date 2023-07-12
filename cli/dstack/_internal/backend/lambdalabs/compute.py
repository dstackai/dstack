import hashlib
import os
import subprocess
import tempfile
import time
from threading import Thread
from typing import Dict, List, Optional, Tuple

import pkg_resources
import yaml

from dstack import version
from dstack._internal.backend.base.compute import WS_PORT, choose_instance_type, get_dstack_runner
from dstack._internal.backend.base.config import BACKEND_CONFIG_FILENAME, RUNNER_CONFIG_FILENAME
from dstack._internal.backend.base.runners import serialize_runner_yaml
from dstack._internal.backend.lambdalabs.api_client import LambdaAPIClient
from dstack._internal.backend.lambdalabs.config import LambdaConfig
from dstack._internal.core.instance import InstanceType, LaunchedInstanceInfo
from dstack._internal.core.job import Job
from dstack._internal.core.request import RequestHead, RequestStatus
from dstack._internal.core.runners import Gpu, Resources, Runner
from dstack._internal.hub.utils.ssh import HUB_PRIVATE_KEY_PATH, get_hub_ssh_public_key

_WAIT_FOR_INSTANCE_ATTEMPTS = 120
_WAIT_FOR_INSTANCE_INTERVAL = 10


_INSTANCE_TYPE_TO_GPU_DATA_MAP = {
    "gpu_1x_h100_pcie": {
        "name": "H100",
        "count": 1,
        "memory_mib": 80 * 1024,
    },
    "gpu_8x_a100_80gb_sxm4": {
        "name": "A100",
        "count": 8,
        "memory_mib": 80 * 1024,
    },
    "gpu_1x_a10": {
        "name": "A10",
        "count": 1,
        "memory_mib": 24 * 1024,
    },
    "gpu_1x_rtx6000": {
        "name": "RTX6000",
        "count": 1,
        "memory_mib": 24 * 1024,
    },
    "gpu_1x_a100": {
        "name": "A100",
        "count": 1,
        "memory_mib": 40 * 1024,
    },
    "gpu_1x_a100_sxm4": {
        "name": "A100",
        "count": 1,
        "memory_mib": 40 * 1024,
    },
    "gpu_2x_a100": {
        "name": "A100",
        "count": 2,
        "memory_mib": 40 * 1024,
    },
    "gpu_4x_a100": {
        "name": "A100",
        "count": 4,
        "memory_mib": 40 * 1024,
    },
    "gpu_8x_a100": {
        "name": "A100",
        "count": 8,
        "memory_mib": 40 * 1024,
    },
    "gpu_1x_a6000": {
        "name": "A6000",
        "count": 1,
        "memory_mib": 48 * 1024,
    },
    "gpu_2x_a6000": {
        "name": "A6000",
        "count": 2,
        "memory_mib": 48 * 1024,
    },
    "gpu_4x_a6000": {
        "name": "A6000",
        "count": 4,
        "memory_mib": 48 * 1024,
    },
    "gpu_8x_v100": {
        "name": "V100",
        "count": 8,
        "memory_mib": 16 * 1024,
    },
}


class LambdaCompute:
    def __init__(self, lambda_config: LambdaConfig):
        self.lambda_config = lambda_config
        self.api_client = LambdaAPIClient(lambda_config.api_key)

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        instance_info = _get_instance_info(self.api_client, request_id)
        if instance_info is None or instance_info["status"] == "terminated":
            return RequestHead(job_id=job.job_id, status=RequestStatus.TERMINATED)
        return RequestHead(
            job_id=job.job_id,
            status=RequestStatus.RUNNING,
        )

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        instance_types = _list_instance_types(self.api_client, self.lambda_config.regions)
        return choose_instance_type(
            instance_types=instance_types,
            requirements=job.requirements,
        )

    def run_instance(self, job: Job, instance_type: InstanceType) -> LaunchedInstanceInfo:
        region = _get_instance_region(instance_type, self.lambda_config.regions)
        instance_id = _run_instance(
            api_client=self.api_client,
            region_name=region,
            instance_type_name=instance_type.instance_name,
            user_ssh_key=job.ssh_key_pub,
            hub_ssh_key=get_hub_ssh_public_key(),
            instance_name=_get_instance_name(job),
            launch_script=_get_launch_script(self.lambda_config, job, instance_type),
        )
        return LaunchedInstanceInfo(request_id=instance_id, location=region)

    def terminate_instance(self, runner: Runner):
        self.api_client.terminate_instances(instance_ids=[runner.request_id])

    def cancel_spot_request(self, runner: Runner):
        pass


def _list_instance_types(api_client: LambdaAPIClient, regions: List[str]) -> List[InstanceType]:
    instance_types_data = api_client.list_instance_types()
    instance_types = []
    for instance_type_data in instance_types_data.values():
        instance_type = _instance_type_data_to_instance_type(instance_type_data)
        if instance_type is None:
            continue
        if _get_instance_region(instance_type, regions) is not None:
            instance_types.append(instance_type)
    return instance_types


def _get_instance_info(api_client: LambdaAPIClient, instance_id: str) -> Optional[Dict]:
    instances = api_client.list_instances()
    instance_id_to_instance_map = {i["id"]: i for i in instances}
    instance = instance_id_to_instance_map.get(instance_id)
    if instance is None:
        return None
    return instance


def _instance_type_data_to_instance_type(instance_type_data: Dict) -> Optional[InstanceType]:
    instance_type = instance_type_data["instance_type"]
    regions_data = instance_type_data["regions_with_capacity_available"]
    regions = [r["name"] for r in regions_data]
    instance_type_specs = instance_type["specs"]
    gpus = _get_instance_type_gpus(instance_type["name"])
    if gpus is None:
        return None
    return InstanceType(
        instance_name=instance_type["name"],
        resources=Resources(
            cpus=instance_type_specs["vcpus"],
            memory_mib=instance_type_specs["memory_gib"] * 1024,
            gpus=gpus,
            spot=False,
            local=False,
        ),
        available_regions=regions,
    )


def _get_instance_type_gpus(instance_type_name: str) -> Optional[List[Gpu]]:
    gpu_data = _INSTANCE_TYPE_TO_GPU_DATA_MAP.get(instance_type_name)
    if gpu_data is None:
        return None
    return [
        Gpu(name=gpu_data["name"], memory_mib=gpu_data["memory_mib"])
        for _ in range(gpu_data["count"])
    ]


def _get_instance_region(instance_type: InstanceType, regions: List[str]) -> Optional[str]:
    for r in instance_type.available_regions:
        if r in regions:
            return r
    return None


def _get_instance_name(job: Job) -> str:
    return f"dstack-{job.run_name}"


def _get_launch_script(lambda_config: LambdaConfig, job: Job, instance_type: InstanceType) -> str:
    config_content = yaml.dump(lambda_config.dict()).replace("\n", "\\n")
    runner_content = serialize_runner_yaml(job.runner_id, instance_type.resources, 3000, 4000)
    return f"""#!/bin/sh
mkdir -p /root/.dstack/
echo '{config_content}' > /root/.dstack/{BACKEND_CONFIG_FILENAME}
echo '{runner_content}' > /root/.dstack/{RUNNER_CONFIG_FILENAME}
echo 'hostname: HOSTNAME_PLACEHOLDER' >> /root/.dstack/{RUNNER_CONFIG_FILENAME}
{get_dstack_runner()}
HOME=/root nohup dstack-runner --log-level 6 start --http-port {WS_PORT}
"""


def _run_instance(
    api_client: LambdaAPIClient,
    region_name: str,
    instance_type_name: str,
    user_ssh_key: str,
    hub_ssh_key: str,
    instance_name: str,
    launch_script: str,
) -> str:
    _, hub_key_name = _add_ssh_keys(api_client, user_ssh_key, hub_ssh_key)
    instances_ids = api_client.launch_instances(
        region_name=region_name,
        instance_type_name=instance_type_name,
        ssh_key_names=[hub_key_name],
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
            "user_ssh_key": user_ssh_key,
            "launch_script": launch_script,
        },
        daemon=True,
    )
    thread.start()
    return instance_id


def _add_ssh_keys(
    api_client: LambdaAPIClient, user_ssh_key: str, hub_ssh_key: str
) -> Tuple[str, str]:
    ssh_keys = api_client.list_ssh_keys()
    ssh_key_names = [k["name"] for k in ssh_keys]
    user_key_name = _add_ssh_key(api_client, ssh_key_names, user_ssh_key)
    hub_key_name = _add_ssh_key(api_client, ssh_key_names, hub_ssh_key)
    return user_key_name, hub_key_name


def _add_ssh_key(api_client: LambdaAPIClient, ssh_key_names: str, public_key: str) -> str:
    key_name = _get_ssh_key_name(public_key)
    if key_name in ssh_key_names:
        return key_name
    api_client.add_ssh_key(name=key_name, public_key=public_key)
    return key_name


def _get_ssh_key_name(public_key: str) -> str:
    return hashlib.sha1(public_key.encode()).hexdigest()[-16:]


def _wait_for_instance(
    api_client: LambdaAPIClient,
    instance_id: str,
) -> Dict:
    for _ in range(_WAIT_FOR_INSTANCE_ATTEMPTS):
        instance_info = _get_instance_info(api_client, instance_id)
        if instance_info is None or instance_info["status"] != "booting":
            return instance_info
        time.sleep(_WAIT_FOR_INSTANCE_INTERVAL)


def _start_runner(hostname: str, user_ssh_key: str, launch_script: str):
    _setup_instance(hostname, user_ssh_key)
    _launch_runner(hostname, launch_script)


def _setup_instance(hostname: str, user_ssh_key: str):
    setup_script_path = pkg_resources.resource_filename(
        "dstack._internal", "scripts/setup_lambda.sh"
    )
    _run_ssh_command(hostname=hostname, commands="mkdir /home/ubuntu/.dstack")
    _run_scp_command(hostname=hostname, source=setup_script_path, target="/home/ubuntu/.dstack")
    # Lambda API allows specifying only one ssh key,
    # so we have to update authorized_keys manually to add the user key
    setup_commands = (
        "chmod +x .dstack/setup_lambda.sh && "
        f"{_get_setup_command()} && "
        f"echo '{user_ssh_key}' >> /home/ubuntu/.ssh/authorized_keys"
    )
    _run_ssh_command(hostname=hostname, commands=setup_commands)


def _get_setup_command() -> str:
    if not version.__is_release__:
        return "ENVIRONMENT=stage RUNNER_VERSION=latest .dstack/setup_lambda.sh"
    return f"ENVIRONMENT=prod RUNNER_VERSION={version.__version__} .dstack/setup_lambda.sh"


def _launch_runner(hostname: str, launch_script: str):
    launch_script = launch_script.replace("HOSTNAME_PLACEHOLDER", hostname)
    with tempfile.NamedTemporaryFile("w+") as f:
        f.write(launch_script)
        f.flush()
        filepath = os.path.join(tempfile.gettempdir(), f.name)
        _run_scp_command(
            hostname=hostname, source=filepath, target="/home/ubuntu/.dstack/launch_runner.sh"
        )
    _run_ssh_command(
        hostname=hostname,
        commands="chmod +x .dstack/launch_runner.sh && sudo .dstack/launch_runner.sh",
    )


def _run_ssh_command(hostname: str, commands: str):
    subprocess.run(
        [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-i",
            HUB_PRIVATE_KEY_PATH,
            f"ubuntu@{hostname}",
            commands,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _run_scp_command(hostname: str, source: str, target: str):
    subprocess.run(
        [
            "scp",
            "-o",
            "StrictHostKeyChecking=no",
            "-i",
            HUB_PRIVATE_KEY_PATH,
            source,
            f"ubuntu@{hostname}:{target}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
