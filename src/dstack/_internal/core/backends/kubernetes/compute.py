import subprocess
import tempfile
import threading
import time
from typing import Dict, List, Optional, Tuple

from gpuhunt import KNOWN_NVIDIA_GPUS, AcceleratorVendor
from kubernetes import client

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithGatewaySupport,
    generate_unique_gateway_instance_name,
    generate_unique_instance_name_for_job,
    get_docker_commands,
    get_dstack_gateway_commands,
)
from dstack._internal.core.backends.base.offers import match_requirements
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesConfig,
    KubernetesNetworkingConfig,
)
from dstack._internal.core.backends.kubernetes.utils import (
    get_api_from_config_data,
    get_cluster_public_ip,
)
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType

# TODO: update import as KNOWN_GPUS becomes public
from dstack._internal.core.models.gateways import (
    GatewayComputeConfiguration,
    GatewayProvisioningData,
)
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceType,
    Resources,
    SSHConnectionParams,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.common import parse_memory
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

JUMP_POD_SSH_PORT = 22
DEFAULT_NAMESPACE = "default"

NVIDIA_GPU_NAME_TO_GPU_INFO = {gpu.name: gpu for gpu in KNOWN_NVIDIA_GPUS}
NVIDIA_GPU_NAMES = NVIDIA_GPU_NAME_TO_GPU_INFO.keys()


class KubernetesCompute(
    ComputeWithGatewaySupport,
    Compute,
):
    def __init__(self, config: KubernetesConfig):
        super().__init__()
        self.config = config.copy()
        networking_config = self.config.networking
        if networking_config is None:
            networking_config = KubernetesNetworkingConfig()
        self.networking_config = networking_config
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
                instance_runtime=InstanceRuntime.RUNNER,
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
        volumes: List[Volume],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name_for_job(run, job)
        commands = get_docker_commands(
            [run.run_spec.ssh_key_pub.strip(), project_ssh_public_key.strip()]
        )
        # Before running a job, ensure a jump pod service is running.
        # There is a one jump pod per Kubernetes backend that is used
        # as an ssh proxy jump to connect to all other services in Kubernetes.
        # Setup jump pod in a separate thread to avoid long-running run_job.
        # In case the thread fails, the job will be failed and resubmitted.
        jump_pod_hostname = self.networking_config.ssh_host
        if jump_pod_hostname is None:
            jump_pod_hostname = get_cluster_public_ip(self.api)
            if jump_pod_hostname is None:
                raise ComputeError(
                    "Failed to acquire an IP for jump pod automatically. "
                    "Specify ssh_host for Kubernetes backend."
                )
        jump_pod_port, created = _create_jump_pod_service_if_not_exists(
            api=self.api,
            project_name=run.project_name,
            ssh_public_keys=[project_ssh_public_key.strip(), run.run_spec.ssh_key_pub.strip()],
            jump_pod_port=self.networking_config.ssh_port,
        )
        if not created:
            threading.Thread(
                target=_continue_setup_jump_pod,
                kwargs={
                    "api": self.api,
                    "project_name": run.project_name,
                    "project_ssh_private_key": project_ssh_private_key.strip(),
                    "user_ssh_public_key": run.run_spec.ssh_key_pub.strip(),
                    "jump_pod_host": jump_pod_hostname,
                    "jump_pod_port": jump_pod_port,
                },
            ).start()
        self.api.create_namespaced_pod(
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
                                    container_port=DSTACK_RUNNER_SSH_PORT,
                                )
                            ],
                            security_context=client.V1SecurityContext(
                                # TODO(#1535): support non-root images properly
                                run_as_user=0,
                                run_as_group=0,
                            ),
                            # TODO: Pass cpu, memory, gpu as requests.
                            # Beware that node capacity != allocatable, so
                            # if the node has 2xCPU – then cpu=2 request will probably fail.
                            resources=client.V1ResourceRequirements(requests={}),
                        )
                    ]
                ),
            ),
        )
        service_response = self.api.create_namespaced_service(
            namespace=DEFAULT_NAMESPACE,
            body=client.V1Service(
                metadata=client.V1ObjectMeta(name=_get_pod_service_name(instance_name)),
                spec=client.V1ServiceSpec(
                    type="ClusterIP",
                    selector={"app.kubernetes.io/name": instance_name},
                    ports=[client.V1ServicePort(port=DSTACK_RUNNER_SSH_PORT)],
                ),
            ),
        )
        service_ip = service_response.spec.cluster_ip
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_name,
            hostname=service_ip,
            internal_ip=None,
            region="local",
            price=instance_offer.price,
            username="root",
            ssh_port=DSTACK_RUNNER_SSH_PORT,
            dockerized=False,
            ssh_proxy=SSHConnectionParams(
                hostname=jump_pod_hostname,
                username="root",
                port=jump_pod_port,
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

    def create_gateway(
        self,
        configuration: GatewayComputeConfiguration,
    ) -> GatewayProvisioningData:
        # Gateway creation is currently limited to Kubernetes with Load Balancer support.
        # If the cluster does not support Load Balancer, the service will be provisioned but
        # the external IP/hostname will never be allocated.

        # TODO: This implementation is only tested on EKS. Test other managed Kubernetes.

        # TODO: By default EKS creates a Classic Load Balancer for Load Balancer services.
        # Consider deploying an NLB. It seems it requires some extra configuration on the cluster:
        # https://docs.aws.amazon.com/eks/latest/userguide/network-load-balancing.html
        instance_name = generate_unique_gateway_instance_name(configuration)
        commands = _get_gateway_commands(authorized_keys=[configuration.ssh_key_pub])
        self.api.create_namespaced_pod(
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
                            image="ubuntu:22.04",
                            command=["/bin/sh"],
                            args=["-c", " && ".join(commands)],
                            ports=[
                                client.V1ContainerPort(
                                    container_port=22,
                                ),
                                client.V1ContainerPort(
                                    container_port=80,
                                ),
                                client.V1ContainerPort(
                                    container_port=443,
                                ),
                            ],
                        )
                    ]
                ),
            ),
        )
        self.api.create_namespaced_service(
            namespace=DEFAULT_NAMESPACE,
            body=client.V1Service(
                metadata=client.V1ObjectMeta(
                    name=_get_pod_service_name(instance_name),
                ),
                spec=client.V1ServiceSpec(
                    type="LoadBalancer",
                    selector={"app.kubernetes.io/name": instance_name},
                    ports=[
                        client.V1ServicePort(
                            name="ssh",
                            port=22,
                            target_port=22,
                        ),
                        client.V1ServicePort(
                            name="http",
                            port=80,
                            target_port=80,
                        ),
                        client.V1ServicePort(
                            name="https",
                            port=443,
                            target_port=443,
                        ),
                    ],
                ),
            ),
        )
        hostname = _wait_for_load_balancer_hostname(
            api=self.api, service_name=_get_pod_service_name(instance_name)
        )
        if hostname is None:
            self.terminate_instance(instance_name, region="-")
            raise ComputeError(
                "Failed to get gateway hostname. "
                "Ensure the Kubernetes cluster supports Load Balancer services."
            )
        return GatewayProvisioningData(
            instance_id=instance_name,
            ip_address=hostname,
            region="-",
        )

    def terminate_gateway(
        self,
        instance_id: str,
        configuration: GatewayComputeConfiguration,
        backend_data: Optional[str] = None,
    ):
        self.terminate_instance(
            instance_id=instance_id,
            region=configuration.region,
            backend_data=backend_data,
        )


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
    for known_gpu_name in NVIDIA_GPU_NAMES:
        if known_gpu_name.lower() in gpu_product.lower().split("-"):
            gpu_name = known_gpu_name
            break
    if gpu_name is None:
        return []
    gpu_info = NVIDIA_GPU_NAME_TO_GPU_INFO[gpu_name]
    gpu_memory = gpu_info.memory * 1024
    # A100 may come in two variants
    if "40GB" in gpu_product:
        gpu_memory = 40 * 1024
    return [
        Gpu(vendor=AcceleratorVendor.NVIDIA, name=gpu_name, memory_mib=gpu_memory)
        for _ in range(gpu_count)
    ]


def _continue_setup_jump_pod(
    api: client.CoreV1Api,
    project_name: str,
    project_ssh_private_key: str,
    user_ssh_public_key: str,
    jump_pod_host: str,
    jump_pod_port: int,
):
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
    ssh_public_keys: List[str],
    jump_pod_port: Optional[int],
) -> Tuple[int, bool]:
    created = False
    try:
        service = api.read_namespaced_service(
            name=_get_jump_pod_service_name(project_name),
            namespace=DEFAULT_NAMESPACE,
        )
    except client.ApiException as e:
        if e.status == 404:
            service = _create_jump_pod_service(
                api=api,
                project_name=project_name,
                ssh_public_keys=ssh_public_keys,
                jump_pod_port=jump_pod_port,
            )
            created = True
        else:
            raise
    return service.spec.ports[0].node_port, created


def _create_jump_pod_service(
    api: client.CoreV1Api,
    project_name: str,
    ssh_public_keys: List[str],
    jump_pod_port: Optional[int],
) -> client.V1Service:
    # TODO use restricted ssh-forwarding-only user for jump pod instead of root.
    commands = _get_jump_pod_commands(authorized_keys=ssh_public_keys)
    pod_name = _get_jump_pod_name(project_name)
    api.create_namespaced_pod(
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
    service_response = api.create_namespaced_service(
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
    return service_response


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


def _wait_for_load_balancer_hostname(
    api: client.CoreV1Api,
    service_name: str,
    timeout_seconds: int = 120,
) -> Optional[str]:
    start_time = time.time()
    while True:
        try:
            service = api.read_namespaced_service(name=service_name, namespace=DEFAULT_NAMESPACE)
        except client.ApiException as e:
            if e.status != 404:
                raise
        else:
            if service.status.load_balancer.ingress is not None:
                return service.status.load_balancer.ingress[0].hostname
        elapsed_time = time.time() - start_time
        if elapsed_time >= timeout_seconds:
            logger.warning("Timeout waiting for load balancer %s to get ip", service_name)
            return None
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


def _get_gateway_commands(authorized_keys: List[str]) -> List[str]:
    authorized_keys_content = "\n".join(authorized_keys).strip()
    gateway_commands = " && ".join(get_dstack_gateway_commands())
    commands = [
        # install packages
        "apt-get update && apt-get install -y sudo wget openssh-server nginx python3.10-venv libaugeas0",
        # install docker-systemctl-replacement
        "wget https://raw.githubusercontent.com/gdraheim/docker-systemctl-replacement/b18d67e521f0d1cf1d705dbb8e0416bef23e377c/files/docker/systemctl3.py -O /usr/bin/systemctl",
        "chmod + /usr/bin/systemctl",
        # install certbot
        "python3 -m venv /root/certbotvenv/",
        "/root/certbotvenv/bin/pip install certbot-nginx",
        "ln -s /root/certbotvenv/bin/certbot /usr/bin/certbot",
        # prohibit password authentication
        'sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config',
        # set up ubuntu user
        "adduser ubuntu",
        "usermod -aG sudo ubuntu",
        "echo 'ubuntu ALL=(ALL:ALL) NOPASSWD: ALL' | tee /etc/sudoers.d/ubuntu",
        # create ssh dirs and add public key
        "mkdir -p /run/sshd /home/ubuntu/.ssh",
        "chmod 700 /home/ubuntu/.ssh",
        f"echo '{authorized_keys_content}' > /home/ubuntu/.ssh/authorized_keys",
        "chmod 600 /home/ubuntu/.ssh/authorized_keys",
        "chown -R ubuntu:ubuntu /home/ubuntu/.ssh",
        # regenerate host keys
        "rm -rf /etc/ssh/ssh_host_*",
        "ssh-keygen -A > /dev/null",
        # start sshd
        "/usr/sbin/sshd -p 22 -o PermitUserEnvironment=yes",
        # run gateway
        f"su ubuntu -c '{gateway_commands}'",
        "sleep infinity",
    ]
    return commands


def _run_ssh_command(hostname: str, port: int, ssh_private_key: str, command: str):
    with tempfile.NamedTemporaryFile("w+", 0o600) as f:
        f.write(ssh_private_key)
        f.flush()
        subprocess.run(
            [
                "ssh",
                "-F",
                "none",
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
