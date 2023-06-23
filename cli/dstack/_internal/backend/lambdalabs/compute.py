import time
from typing import Dict, List, Optional

from dstack._internal.backend.base.compute import choose_instance_type
from dstack._internal.backend.lambdalabs.api_client import LambdaAPIClient
from dstack._internal.core.instance import InstanceType
from dstack._internal.core.job import Job
from dstack._internal.core.request import RequestHead, RequestStatus
from dstack._internal.core.runners import Gpu, Resources


class LambdaCompute:
    def __init__(self, api_key: str):
        self.api_client = LambdaAPIClient(api_key)

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        instance_info = _get_instance_info(self.api_client, request_id)
        if instance_info is None or instance_info["status"] == "terminated":
            return RequestHead(job_id=job.job_id, status=RequestStatus.TERMINATED)
        return RequestHead(
            job_id=job.job_id,
            status=RequestStatus.RUNNING,
        )

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        instance_types = _list_instance_types(self.api_client)
        return choose_instance_type(
            instance_types=instance_types,
            requirements=job.requirements,
        )

    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        return _run_instance(
            api_client=self.api_client,
            region_name="us-west-1",
            instance_type_name=instance_type.instance_name,
            ssh_key_name="dstack_victor",
            instance_name=_get_instance_name(job),
        )

    def terminate_instance(self, request_id: str):
        pass

    def cancel_spot_request(self, request_id: str):
        pass


def _list_instance_types(api_client: LambdaAPIClient) -> List[InstanceType]:
    instance_types_data = api_client.list_instance_types()
    instance_types = []
    for instance_type_data in instance_types_data.values():
        instance_type = _instance_type_data_to_instance_type(instance_type_data)
        if instance_type is not None:
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
    regions = instance_type_data["regions_with_capacity_available"]
    if len(regions) == 0:
        return None
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
    )


_INSTANCE_TYPE_TO_GPU_DATA_MAP = {
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
}


def _get_instance_type_gpus(instance_type_name: str) -> Optional[List[Gpu]]:
    gpu_data = _INSTANCE_TYPE_TO_GPU_DATA_MAP.get(instance_type_name)
    if gpu_data is None:
        return None
    return [
        Gpu(name=gpu_data["name"], memory_mib=gpu_data["memory_mib"])
        for _ in range(gpu_data["count"])
    ]


def _get_instance_name(job: Job) -> str:
    return f"dstack-{job.run_name}"


def _run_instance(
    api_client: LambdaAPIClient,
    region_name: str,
    instance_type_name: str,
    ssh_key_name: str,
    instance_name: str,
) -> str:
    instances_ids = api_client.launch_instances(
        region_name=region_name,
        instance_type_name=instance_type_name,
        ssh_key_names=[ssh_key_name],
        name=instance_name,
        quantity=1,
        file_system_names=[],
    )
    instance_id = instances_ids[0]
    instance_info = _wait_for_instance(api_client, instance_id)
    return instance_id


def _wait_for_instance(
    api_client: LambdaAPIClient,
    instance_id: str,
) -> Dict:
    while True:
        instance_info = _get_instance_info(api_client, instance_id)
        if instance_info is None or instance_info["status"] != "booting":
            return
        time.sleep(10)


def _launch_runner(hostname: str):
    pass
