import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

import requests
from gpuhunt.providers.runpod import RunpodProvider
from requests import Response

from dstack._internal.core.errors import BackendError, BackendInvalidCredentialsError
from dstack._internal.utils.common import get_current_datetime

API_URL = "https://api.runpod.io/graphql"


class RunpodApiClientError(BackendError):
    errors: List[Dict]

    def __init__(self, errors: List[Dict]):
        self.errors = errors
        super().__init__(errors)


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
        resp = self._make_request(
            {
                "query": """
                query myself {
                    myself {
                        id
                        authId
                        email
                    }
                }
                """
            }
        )
        return resp.json()

    def create_pod(
        self,
        name: str,
        image_name: str,
        gpu_type_id: str,
        cloud_type: str,
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
        volume_mount_path: Optional[str] = None,
        env: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None,
        network_volume_id: Optional[str] = None,
        allowed_cuda_versions: Optional[List[str]] = None,
        bid_per_gpu: Optional[float] = None,
    ) -> Dict:
        resp = self._make_request(
            {
                "query": _generate_pod_deployment_mutation(
                    name=name,
                    image_name=image_name,
                    gpu_type_id=gpu_type_id,
                    cloud_type=cloud_type,
                    support_public_ip=support_public_ip,
                    start_ssh=start_ssh,
                    data_center_id=data_center_id,
                    country_code=country_code,
                    gpu_count=gpu_count,
                    volume_in_gb=volume_in_gb,
                    container_disk_in_gb=container_disk_in_gb,
                    min_vcpu_count=min_vcpu_count,
                    min_memory_in_gb=min_memory_in_gb,
                    docker_args=docker_args,
                    ports=ports,
                    volume_mount_path=volume_mount_path,
                    env=env,
                    template_id=template_id,
                    network_volume_id=network_volume_id,
                    allowed_cuda_versions=allowed_cuda_versions,
                    bid_per_gpu=bid_per_gpu,
                )
            }
        )
        data = resp.json()["data"]
        return data["podRentInterruptable"] if bid_per_gpu else data["podFindAndDeployOnDemand"]

    def edit_pod(
        self,
        pod_id: str,
        image_name: str,
        container_disk_in_gb: int,
        container_registry_auth_id: str,
        # Default pod volume is 20GB.
        # RunPod errors if it's not specified for podEditJob.
        volume_in_gb: int = 20,
    ) -> str:
        resp = self._make_request(
            {
                "query": f"""
                mutation {{
                    podEditJob(input: {{
                        podId: "{pod_id}"
                        imageName: "{image_name}"
                        containerDiskInGb: {container_disk_in_gb}
                        containerRegistryAuthId: "{container_registry_auth_id}"
                        volumeInGb: {volume_in_gb}
                    }}) {{
                        id
                    }}
                }}
                """
            }
        )
        return resp.json()["data"]["podEditJob"]["id"]

    def get_pod(self, pod_id: str) -> Dict:
        resp = self._make_request({"query": _generate_pod_query(pod_id)})
        data = resp.json()
        return data["data"]["pod"]

    def terminate_pod(self, pod_id: str) -> Dict:
        resp = self._make_request({"query": _generate_pod_terminate_mutation(pod_id)})
        data = resp.json()
        return data["data"]

    def get_container_registry_auths(self) -> List[Dict]:
        resp = self._make_request(
            {
                "query": """
                query myself {
                    myself {
                        containerRegistryCreds {
                            id,
                            name
                        }
                    }
                }
                """
            }
        )
        return resp.json()["data"]["myself"]["containerRegistryCreds"]

    def add_container_registry_auth(self, name: str, username: str, password: str) -> str:
        resp = self._make_request(
            {
                "query": f"""
                mutation {{
                    saveRegistryAuth(
                        input: {{
                            name: "{name}",
                            username: "{username}",
                            password: "{password}"
                        }}
                    ) {{
                        id
                    }}
                }}
                """
            }
        )
        return resp.json()["data"]["saveRegistryAuth"]["id"]

    def delete_container_registry_auth(self, auth_id: str) -> None:
        self._make_request(
            {
                "query": f"""
                mutation {{
                    deleteRegistryAuth(
                        registryAuthId: "{auth_id}"
                    )
                }}
                """
            }
        )

    def get_network_volume(self, volume_id: str) -> Optional[Dict]:
        response = self._make_request(
            {
                "query": """
                query getMyVolumes {
                    myself {
                        networkVolumes {
                            id,
                            name,
                            size,
                            dataCenter {
                              id
                              name
                            }
                        }
                    }
                }
                """
            }
        )
        network_volumes = response.json()["data"]["myself"]["networkVolumes"]
        for vol in network_volumes:
            if vol["id"] == volume_id:
                return vol
        return None

    def create_network_volume(self, name: str, region: str, size: int) -> str:
        response = self._make_request(
            {
                "query": f"""
                mutation {{
                    createNetworkVolume(
                        input: {{
                            name: "{name}",
                            size: {size},
                            dataCenterId: "{region}"
                        }}
                    ) {{
                       id
                    }}
                }}
                """
            }
        )
        return response.json()["data"]["createNetworkVolume"]["id"]

    def delete_network_volume(self, volume_id: str) -> None:
        self._make_request(
            {
                "query": f"""
                mutation {{
                    deleteNetworkVolume(
                        input: {{
                            id: "{volume_id}"
                        }}
                    )
                }}
                """
            }
        )

    def create_cluster(
        self,
        cluster_name: str,
        gpu_type_id: str,
        pod_count: int,
        gpu_count_per_pod: int,
        image_name: str,
        deploy_cost: str,
        template_id: Optional[str] = None,
        cluster_type: str = "TRAINING",
        network_volume_id: Optional[str] = None,
        volume_in_gb: Optional[int] = None,
        throughput: Optional[int] = None,
        allowed_cuda_versions: Optional[List[str]] = None,
        volume_key: Optional[str] = None,
        data_center_id: Optional[str] = None,
        start_jupyter: bool = False,
        start_ssh: bool = False,
        container_disk_in_gb: Optional[int] = None,
        docker_args: Optional[str] = None,
        env: Optional[Dict[str, Any]] = None,
        volume_mount_path: Optional[str] = None,
        ports: Optional[str] = None,
    ) -> Dict:
        resp = self._make_request(
            {
                "query": _generate_create_cluster_mutation(
                    cluster_name=cluster_name,
                    gpu_type_id=gpu_type_id,
                    pod_count=pod_count,
                    gpu_count_per_pod=gpu_count_per_pod,
                    image_name=image_name,
                    cluster_type=cluster_type,
                    deploy_cost=deploy_cost,
                    template_id=template_id,
                    network_volume_id=network_volume_id,
                    volume_in_gb=volume_in_gb,
                    throughput=throughput,
                    allowed_cuda_versions=allowed_cuda_versions,
                    volume_key=volume_key,
                    data_center_id=data_center_id,
                    start_jupyter=start_jupyter,
                    start_ssh=start_ssh,
                    container_disk_in_gb=container_disk_in_gb,
                    docker_args=docker_args,
                    env=env,
                    volume_mount_path=volume_mount_path,
                    ports=ports,
                )
            }
        )
        data = resp.json()["data"]
        return data["createCluster"]

    def delete_cluster(self, cluster_id: str) -> bool:
        resp = self._make_request({"query": _generate_delete_cluster_mutation(cluster_id)})
        data = resp.json()["data"]
        return data["deleteCluster"]

    def _make_request(self, data: Optional[Dict[str, Any]] = None) -> Response:
        try:
            response = requests.request(
                method="POST",
                url=f"{API_URL}?api_key={self.api_key}",
                json=data,
                timeout=120,
            )
            response.raise_for_status()
            response_json = response.json()
            # RunPod returns 200 on client errors
            if "errors" in response_json:
                raise RunpodApiClientError(errors=response_json["errors"])
            return response
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (
                requests.codes.forbidden,
                requests.codes.unauthorized,
            ):
                raise BackendInvalidCredentialsError(e.response.text)
            raise

    def wait_for_instance(self, instance_id: str) -> Optional[Dict]:
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


def _generate_pod_query(pod_id: str) -> str:
    """
    Generate a query for a specific GPU type
    """

    return f"""
    query pod {{
        pod(input: {{podId: "{pod_id}"}}) {{
            id
            clusterIp
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


def _generate_pod_deployment_mutation(
    name: str,
    image_name: str,
    gpu_type_id: str,
    cloud_type: str,
    support_public_ip: bool = True,
    start_ssh: bool = True,
    data_center_id: Optional[str] = None,
    country_code: Optional[str] = None,
    gpu_count: Optional[int] = None,
    volume_in_gb: Optional[int] = None,
    container_disk_in_gb: Optional[int] = None,
    min_vcpu_count: Optional[int] = None,
    min_memory_in_gb: Optional[int] = None,
    docker_args: Optional[str] = None,
    ports: Optional[str] = None,
    volume_mount_path: Optional[str] = None,
    env: Optional[Dict[str, Any]] = None,
    template_id: Optional[str] = None,
    network_volume_id: Optional[str] = None,
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

    input_fields.append(f'minCudaVersion: "{RunpodProvider.MIN_CUDA_VERSION}"')

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


def _generate_pod_terminate_mutation(pod_id: str) -> str:
    """
    Generates a mutation to terminate a pod.
    """
    return f"""
    mutation {{
        podTerminate(input: {{ podId: "{pod_id}" }})
    }}
    """


def _generate_delete_cluster_mutation(cluster_id: str) -> str:
    """
    Generates a mutation to delete a cluster.
    """
    return f"""
    mutation {{
        deleteCluster(
            input: {{
                id: "{cluster_id}"
            }}
        )
    }}
    """


def _generate_create_cluster_mutation(
    cluster_name: str,
    gpu_type_id: str,
    pod_count: int,
    gpu_count_per_pod: int,
    image_name: str,
    cluster_type: str,
    deploy_cost: str,
    template_id: Optional[str] = None,
    network_volume_id: Optional[str] = None,
    volume_in_gb: Optional[int] = None,
    throughput: Optional[int] = None,
    allowed_cuda_versions: Optional[List[str]] = None,
    volume_key: Optional[str] = None,
    data_center_id: Optional[str] = None,
    start_jupyter: bool = False,
    start_ssh: bool = False,
    container_disk_in_gb: Optional[int] = None,
    docker_args: Optional[str] = None,
    env: Optional[Dict[str, Any]] = None,
    volume_mount_path: Optional[str] = None,
    ports: Optional[str] = None,
) -> str:
    """
    Generates a mutation to create a cluster.
    """
    input_fields = []

    # ------------------------------ Required Fields ----------------------------- #
    input_fields.append(f'clusterName: "{cluster_name}"')
    input_fields.append(f'gpuTypeId: "{gpu_type_id}"')
    input_fields.append(f"podCount: {pod_count}")
    input_fields.append(f'imageName: "{image_name}"')
    input_fields.append(f"type: {cluster_type}")
    input_fields.append(f"gpuCountPerPod: {gpu_count_per_pod}")
    # If deploy_cost is not specified, Runpod returns Insufficient resources error.
    input_fields.append(f"deployCost: {deploy_cost}")

    # ------------------------------ Optional Fields ----------------------------- #
    if template_id is not None:
        input_fields.append(f'templateId: "{template_id}"')
    if network_volume_id is not None:
        input_fields.append(f'networkVolumeId: "{network_volume_id}"')
    if volume_in_gb is not None:
        input_fields.append(f"volumeInGb: {volume_in_gb}")
    if throughput is not None:
        input_fields.append(f"throughput: {throughput}")
    if allowed_cuda_versions is not None:
        allowed_cuda_versions_string = ", ".join(
            [f'"{version}"' for version in allowed_cuda_versions]
        )
        input_fields.append(f"allowedCudaVersions: [{allowed_cuda_versions_string}]")
    if volume_key is not None:
        input_fields.append(f'volumeKey: "{volume_key}"')
    if data_center_id is not None:
        input_fields.append(f'dataCenterId: "{data_center_id}"')
    if start_jupyter:
        input_fields.append("startJupyter: true")
    if start_ssh:
        input_fields.append("startSsh: true")
    if container_disk_in_gb is not None:
        input_fields.append(f"containerDiskInGb: {container_disk_in_gb}")
    if docker_args is not None:
        input_fields.append(f'dockerArgs: "{docker_args}"')
    if env is not None:
        env_string = ", ".join(
            [f'{{ key: "{key}", value: "{value}" }}' for key, value in env.items()]
        )
        input_fields.append(f"env: [{env_string}]")
    if volume_mount_path is not None:
        input_fields.append(f'volumeMountPath: "{volume_mount_path}"')
    if ports is not None:
        ports = ports.replace(" ", "")
        input_fields.append(f'ports: "{ports}"')

    input_fields.append(f'minCudaVersion: "{RunpodProvider.MIN_CUDA_VERSION}"')

    # Format input fields
    input_string = ", ".join(input_fields)
    return f"""
        mutation {{
          createCluster(
            input: {{
              {input_string}
            }}
          ) {{
            id
            name
            pods {{
              id
              clusterIp
              lastStatusChange
              imageName
              machine {{
                podHostId
              }}
            }}
          }}
        }}
        """
