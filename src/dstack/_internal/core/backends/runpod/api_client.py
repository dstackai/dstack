import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

import requests
from requests import Response

from dstack._internal.core.errors import BackendError, BackendInvalidCredentialsError
from dstack._internal.utils.common import get_current_datetime

API_URL = "https://api.runpod.io/graphql"


class RunpodApiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def validate_api_key(self) -> bool:
        try:
            self.get_user_details()
        except BackendInvalidCredentialsError:
            return False
        return True

    def get_user_details(self) -> Dict:
        resp = self._make_request({"query": user_details_query, "variable": {}})
        return resp.json()

    def create_pod(
        self,
        name: str,
        image_name: str,
        gpu_type_id: str,
        cloud_type: str = "ALL",
        support_public_ip: bool = True,
        start_ssh: bool = True,
        data_center_id: Optional[str] = None,
        country_code: Optional[str] = None,
        gpu_count: int = 1,
        volume_in_gb: int = 0,
        container_disk_in_gb: Optional[int] = None,
        min_vcpu_count: int = 1,
        min_memory_in_gb: int = 1,
        docker_args: str = "",
        ports: Optional[str] = None,
        volume_mount_path: str = "/runpod-volume",
        env: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None,
        network_volume_id: Optional[str] = None,
        allowed_cuda_versions: Optional[List[str]] = None,
        bid_per_gpu: Optional[float] = None,
    ) -> Dict:
        resp = self._make_request(
            {
                "query": generate_pod_deployment_mutation(
                    name,
                    image_name,
                    gpu_type_id,
                    cloud_type,
                    support_public_ip,
                    start_ssh,
                    data_center_id,
                    country_code,
                    gpu_count,
                    volume_in_gb,
                    container_disk_in_gb,
                    min_vcpu_count,
                    min_memory_in_gb,
                    docker_args,
                    ports,
                    volume_mount_path,
                    env,
                    template_id,
                    network_volume_id,
                    allowed_cuda_versions,
                    bid_per_gpu,
                )
            }
        )
        data = resp.json()["data"]
        return data["podRentInterruptable"] if bid_per_gpu else data["podFindAndDeployOnDemand"]

    def get_pod(self, pod_id: str) -> Dict:
        resp = self._make_request({"query": generate_pod_query(pod_id)})
        data = resp.json()
        return data["data"]["pod"]

    def terminate_pod(self, pod_id: str) -> Dict:
        resp = self._make_request({"query": generate_pod_terminate_mutation(pod_id)})
        data = resp.json()
        return data["data"]

    def _make_request(self, data: Any = None) -> Response:
        try:
            # TODO: fix S113 by setting an adequate timeout here or in every method
            response = requests.request(  # noqa: S113
                method="POST",
                url=f"{API_URL}?api_key={self.api_key}",
                json=data,
            )
            response.raise_for_status()
            if "errors" in response.json():
                if "podTerminate" in response.json()["errors"][0]["path"]:
                    raise BackendError("Instance Not Found")
                raise BackendError(response.json()["errors"][0]["message"])
            return response
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (
                requests.codes.forbidden,
                requests.codes.unauthorized,
            ):
                raise BackendInvalidCredentialsError(e.response.text)
            raise

    def wait_for_instance(self, instance_id) -> Optional[Dict]:
        start = get_current_datetime()
        wait_for_instance_interval = 5
        # To change the status to "running," the image must be pulled and then started.
        # We have to wait for 20 minutes while a large image is pulled.
        while get_current_datetime() < (start + timedelta(minutes=20)):
            pod = self.get_pod(instance_id)
            if pod["runtime"] is not None:
                return pod
            time.sleep(wait_for_instance_interval)
        return


user_details_query = """
query myself {
    myself {
        id
        authId
        email
    }
}
"""


def generate_pod_query(pod_id: str) -> str:
    """
    Generate a query for a specific GPU type
    """

    return f"""
    query pod {{
        pod(input: {{podId: "{pod_id}"}}) {{
            id
            containerDiskInGb
            costPerHr
            desiredStatus
            dockerArgs
            dockerId
            env
            gpuCount
            imageName
            lastStatusChange
            machineId
            memoryInGb
            name
            podType
            port
            ports
            uptimeSeconds
            vcpuCount
            volumeInGb
            volumeMountPath
            runtime {{
                ports {{
                    ip
                    isIpPublic
                    privatePort
                    publicPort
                    type
                }}
            }}
            machine {{
                gpuDisplayName
            }}
        }}
    }}
    """


def generate_pod_deployment_mutation(
    name: str,
    image_name: str,
    gpu_type_id: str,
    cloud_type: str = "ALL",
    support_public_ip: bool = True,
    start_ssh: bool = True,
    data_center_id=None,
    country_code=None,
    gpu_count=None,
    volume_in_gb=None,
    container_disk_in_gb=None,
    min_vcpu_count=None,
    min_memory_in_gb=None,
    docker_args=None,
    ports=None,
    volume_mount_path=None,
    env: Optional[Dict[str, Any]] = None,
    template_id=None,
    network_volume_id=None,
    allowed_cuda_versions: Optional[List[str]] = None,
    bid_per_gpu: Optional[float] = None,
) -> str:
    """
    Generates a mutation to deploy pod.
    """
    input_fields = []

    # ------------------------------ Required Fields ----------------------------- #
    input_fields.append(f'name: "{name}"')
    input_fields.append(f'imageName: "{image_name}"')
    input_fields.append(f'gpuTypeId: "{gpu_type_id}"')

    # ------------------------------ Default Fields ------------------------------ #
    input_fields.append(f"cloudType: {cloud_type}")

    if start_ssh:
        input_fields.append("startSsh: true")

    if support_public_ip:
        input_fields.append("supportPublicIp: true")
    else:
        input_fields.append("supportPublicIp: false")

    # ------------------------------ Optional Fields ----------------------------- #
    if bid_per_gpu is not None:
        input_fields.append(f"bidPerGpu: {bid_per_gpu}")
    if data_center_id is not None:
        input_fields.append(f'dataCenterId: "{data_center_id}"')
    if country_code is not None:
        input_fields.append(f'countryCode: "{country_code}"')
    if gpu_count is not None:
        input_fields.append(f"gpuCount: {gpu_count}")
    if volume_in_gb is not None:
        input_fields.append(f"volumeInGb: {volume_in_gb}")
    if container_disk_in_gb is not None:
        input_fields.append(f"containerDiskInGb: {container_disk_in_gb}")
    if min_vcpu_count is not None:
        input_fields.append(f"minVcpuCount: {min_vcpu_count}")
    if min_memory_in_gb is not None:
        input_fields.append(f"minMemoryInGb: {min_memory_in_gb}")
    if docker_args is not None:
        input_fields.append(f'dockerArgs: "{docker_args}"')
    if ports is not None:
        ports = ports.replace(" ", "")
        input_fields.append(f'ports: "{ports}"')
    if volume_mount_path is not None:
        input_fields.append(f'volumeMountPath: "{volume_mount_path}"')
    if env is not None:
        env_string = ", ".join(
            [f'{{ key: "{key}", value: "{value}" }}' for key, value in env.items()]
        )
        input_fields.append(f"env: [{env_string}]")
    if template_id is not None:
        input_fields.append(f'templateId: "{template_id}"')

    if network_volume_id is not None:
        input_fields.append(f'networkVolumeId: "{network_volume_id}"')

    if allowed_cuda_versions is not None:
        allowed_cuda_versions_string = ", ".join(
            [f'"{version}"' for version in allowed_cuda_versions]
        )
        input_fields.append(f"allowedCudaVersions: [{allowed_cuda_versions_string}]")

    pod_deploy = "podFindAndDeployOnDemand" if bid_per_gpu is None else "podRentInterruptable"
    # Format input fields
    input_string = ", ".join(input_fields)
    return f"""
        mutation {{
          {pod_deploy}(
            input: {{
              {input_string}
            }}
          ) {{
            id
            lastStatusChange
            imageName
            machine {{
              podHostId
            }}
          }}
        }}
        """


def generate_pod_terminate_mutation(pod_id: str) -> str:
    """
    Generates a mutation to terminate a pod.
    """
    return f"""
    mutation {{
        podTerminate(input: {{ podId: "{pod_id}" }})
    }}
    """
