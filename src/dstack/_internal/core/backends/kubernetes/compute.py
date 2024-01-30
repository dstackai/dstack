import subprocess
import tempfile
import threading
import time
from typing import Dict, List, Optional

# TODO: update import as KNOWN_GPUS becomes public
from gpuhunt._internal.constraints import KNOWN_GPUS
from kubernetes import client

from dstack._internal.core.backends.base.compute import (
    Compute,
    get_docker_commands,
    get_instance_name,
)
from dstack._internal.core.backends.base.offers import match_requirements
from dstack._internal.core.backends.kubernetes.client import get_api_from_config_data
from dstack._internal.core.backends.kubernetes.config import KubernetesConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedGatewayInfo,
    LaunchedInstanceInfo,
    Resources,
    SSHConnectionParams,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.utils.common import parse_memory
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

RUNNER_SSH_PORT = 10022
JUMP_POD_SSH_PORT = 22
DEFAULT_NAMESPACE = "default"

GPU_NAME_TO_GPU_INFO = {gpu.name: gpu for gpu in KNOWN_GPUS}
GPU_NAMES = GPU_NAME_TO_GPU_INFO.keys()


class KubernetesCompute(Compute):
    def __init__(self, config: KubernetesConfig):
        self.config = config
        self.api = get_api_from_config_data(config.kubeconfig.data)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        nodes = self.api.list_node()
        instance_offers = []
        for node in nodes.items:
            instance_offer = InstanceOfferWithAvailability(
                backend=BackendType.KUBERNETES,
                instance=InstanceType(
                    name=node.metadata.name,
                    resources=Resources(
                        cpus=node.status.capacity["cpu"],
                        memory_mib=int(parse_memory(node.status.capacity["memory"], as_untis="M")),
                        gpus=_get_gpus_from_node_labels(node.metadata.labels),
                        spot=False,
                        disk=Disk(
                            size_mib=int(
                                parse_memory(
                                    node.status.capacity["ephemeral-storage"], as_untis="M"
                                )
                            )
                        ),
                    ),
                ),
                price=0,
                region="-",
                availability=InstanceAvailability.AVAILABLE,
            )
            instance_offers.extend(match_requirements([instance_offer], requirements))
        return instance_offers

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        instance_name = get_instance_name(run, job)
        commands = get_docker_commands(
            [run.run_spec.ssh_key_pub.strip(), project_ssh_public_key.strip()]
        )
        # Setup jump pod in a separate thread to avoid long-running run_job.
        # In case the thread fails, the job will be failed and resubmitted.
        threading.Thread(
            target=_setup_jump_pod,
            kwargs={
                "api": self.api,
                "project_name": run.project_name,
                "project_ssh_public_key": project_ssh_public_key.strip(),
                "project_ssh_private_key": project_ssh_private_key.strip(),
                "user_ssh_public_key": run.run_spec.ssh_key_pub.strip(),
                "jump_pod_host": self.config.networking.ssh_host,
                "jump_pod_port": self.config.networking.ssh_port,
            },
        ).start()
        response = self.api.create_namespaced_pod(
            namespace=DEFAULT_NAMESPACE,
            body=client.V1Pod(
                metadata=client.V1ObjectMeta(
                    name=instance_name,
                    labels={"app.kubernetes.io/name": instance_name},
                ),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name=f"{instance_name}-container",
                            image=job.job_spec.image_name,
                            command=["/bin/sh"],
                            args=["-c", " && ".join(commands)],
                            ports=[
                                client.V1ContainerPort(
                                    container_port=RUNNER_SSH_PORT,
                                )
                            ],
                            # TODO: Pass cpu, memory, gpu as requests.
                            # Beware that node capacity != allocatable, so
                            # if the node has 2xCPU – then cpu=2 request will probably fail.
                            resources=client.V1ResourceRequirements(requests={}),
                        )
                    ]
                ),
            ),
        )
        response = self.api.create_namespaced_service(
            namespace=DEFAULT_NAMESPACE,
            body=client.V1Service(
                metadata=client.V1ObjectMeta(name=_get_pod_service_name(instance_name)),
                spec=client.V1ServiceSpec(
                    type="ClusterIP",
                    selector={"app.kubernetes.io/name": instance_name},
                    ports=[client.V1ServicePort(port=RUNNER_SSH_PORT)],
                ),
            ),
        )
        service_ip = response.spec.cluster_ip
        return LaunchedInstanceInfo(
            instance_id=instance_name,
            ip_address=service_ip,
            region="local",
            username="root",
            ssh_port=RUNNER_SSH_PORT,
            dockerized=False,
            ssh_proxy=SSHConnectionParams(
                hostname=self.config.networking.ssh_host,
                username="root",
                port=self.config.networking.ssh_port,
            ),
            backend_data=None,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        try:
            self.api.delete_namespaced_service(
                name=_get_pod_service_name(instance_id),
                namespace=DEFAULT_NAMESPACE,
                body=client.V1DeleteOptions(),
            )
        except client.ApiException as e:
            if e.status != 404:
                raise
        try:
            self.api.delete_namespaced_pod(
                name=instance_id, namespace=DEFAULT_NAMESPACE, body=client.V1DeleteOptions()
            )
        except client.ApiException as e:
            if e.status != 404:
                raise


def _get_gpus_from_node_labels(labels: Dict) -> List[Gpu]:
    # We rely on https://github.com/NVIDIA/gpu-feature-discovery to detect gpus.
    # Note that "nvidia.com/gpu.product" is not a short gpu name like "T4" or "A100" but a product name
    # from nvidia-smi like "Tesla-T4" or "A100-SXM4-40GB".
    # Thus, we convert the product name to a known gpu name.
    gpu_count = labels.get("nvidia.com/gpu.count")
    gpu_product = labels.get("nvidia.com/gpu.product")
    if gpu_count is None or gpu_product is None:
        return []
    gpu_count = int(gpu_count)
    gpu_name = None
    for known_gpu_name in GPU_NAMES:
        if known_gpu_name.lower() in gpu_product.lower().split("-"):
            gpu_name = known_gpu_name
            break
    if gpu_name is None:
        return []
    gpu_info = GPU_NAME_TO_GPU_INFO[gpu_name]
    gpu_memory = gpu_info.memory * 1024
    # A100 may come in two variants
    if "40GB" in gpu_product:
        gpu_memory = 40 * 1024
    return [Gpu(name=gpu_name, memory_mib=gpu_memory) for _ in range(gpu_count)]


def _setup_jump_pod(
    api: client.CoreV1Api,
    project_name: str,
    project_ssh_public_key: str,
    project_ssh_private_key: str,
    user_ssh_public_key: str,
    jump_pod_host: str,
    jump_pod_port: int,
):
    _create_jump_pod_service_if_not_exists(
        api=api,
        project_name=project_name,
        project_ssh_public_key=project_ssh_public_key,
        jump_pod_port=jump_pod_port,
    )
    _wait_for_pod_ready(
        api=api,
        pod_name=_get_jump_pod_name(project_name),
    )
    _add_authorized_key_to_jump_pod(
        jump_pod_host=jump_pod_host,
        jump_pod_port=jump_pod_port,
        ssh_private_key=project_ssh_private_key,
        ssh_authorized_key=user_ssh_public_key,
    )


def _create_jump_pod_service_if_not_exists(
    api: client.CoreV1Api,
    project_name: str,
    project_ssh_public_key: str,
    jump_pod_port: int,
):
    try:
        api.read_namespaced_service(
            name=_get_jump_pod_service_name(project_name),
            namespace=DEFAULT_NAMESPACE,
        )
    except client.ApiException as e:
        if e.status == 404:
            _create_jump_pod_service(
                api=api,
                project_name=project_name,
                project_ssh_public_key=project_ssh_public_key,
                jump_pod_port=jump_pod_port,
            )
        else:
            raise


def _create_jump_pod_service(
    api: client.CoreV1Api,
    project_name: str,
    project_ssh_public_key: str,
    jump_pod_port: int,
):
    # TODO use restricted ssh-forwarding-only user for jump pod instead of root.
    commands = _get_jump_pod_commands(authorized_keys=[project_ssh_public_key])
    pod_name = _get_jump_pod_name(project_name)
    response = api.create_namespaced_pod(
        namespace=DEFAULT_NAMESPACE,
        body=client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=pod_name,
                labels={"app.kubernetes.io/name": pod_name},
            ),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name=f"{pod_name}-container",
                        # TODO: Choose appropriate image for jump pod
                        image="dstackai/base:py3.11-0.4rc4",
                        command=["/bin/sh"],
                        args=["-c", " && ".join(commands)],
                        ports=[
                            client.V1ContainerPort(
                                container_port=JUMP_POD_SSH_PORT,
                            )
                        ],
                    )
                ]
            ),
        ),
    )
    response = api.create_namespaced_service(
        namespace=DEFAULT_NAMESPACE,
        body=client.V1Service(
            metadata=client.V1ObjectMeta(name=_get_jump_pod_service_name(project_name)),
            spec=client.V1ServiceSpec(
                type="NodePort",
                selector={"app.kubernetes.io/name": pod_name},
                ports=[
                    client.V1ServicePort(
                        port=JUMP_POD_SSH_PORT,
                        target_port=JUMP_POD_SSH_PORT,
                        node_port=jump_pod_port,
                    )
                ],
            ),
        ),
    )


def _get_jump_pod_commands(authorized_keys: List[str]) -> List[str]:
    authorized_keys_content = "\n".join(authorized_keys).strip()
    commands = [
        # prohibit password authentication
        'sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config',
        # create ssh dirs and add public key
        "mkdir -p /run/sshd ~/.ssh",
        "chmod 700 ~/.ssh",
        f"echo '{authorized_keys_content}' > ~/.ssh/authorized_keys",
        "chmod 600 ~/.ssh/authorized_keys",
        # regenerate host keys
        "rm -rf /etc/ssh/ssh_host_*",
        "ssh-keygen -A > /dev/null",
        # start sshd
        f"/usr/sbin/sshd -p {JUMP_POD_SSH_PORT} -o PermitUserEnvironment=yes",
        "sleep infinity",
    ]
    return commands


def _wait_for_pod_ready(
    api: client.CoreV1Api,
    pod_name: str,
    timeout_seconds: int = 300,
):
    start_time = time.time()
    while True:
        try:
            pod = api.read_namespaced_pod(name=pod_name, namespace=DEFAULT_NAMESPACE)
        except client.ApiException as e:
            if e.status != 404:
                raise
        else:
            if pod.status.phase == "Running" and all(
                container_status.ready for container_status in pod.status.container_statuses
            ):
                return True
        elapsed_time = time.time() - start_time
        if elapsed_time >= timeout_seconds:
            logger.warning("Timeout waiting for pod %s to be ready", pod_name)
            return False
        time.sleep(1)


def _add_authorized_key_to_jump_pod(
    jump_pod_host: str,
    jump_pod_port: int,
    ssh_private_key: str,
    ssh_authorized_key: str,
):
    _run_ssh_command(
        hostname=jump_pod_host,
        port=jump_pod_port,
        ssh_private_key=ssh_private_key,
        command=(
            f'if grep -qvF "{ssh_authorized_key}" ~/.ssh/authorized_keys; then '
            f"echo {ssh_authorized_key} >> ~/.ssh/authorized_keys; "
            "fi"
        ),
    )


def _run_ssh_command(hostname: str, port: int, ssh_private_key: str, command: str):
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
                "-p",
                str(port),
                f"root@{hostname}",
                command,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _get_jump_pod_name(project_name: str) -> str:
    return f"{project_name}-ssh-jump-pod"


def _get_jump_pod_service_name(project_name: str) -> str:
    return f"{project_name}-ssh-jump-pod-service"


def _get_pod_service_name(pod_name: str) -> str:
    return f"{pod_name}-service"
