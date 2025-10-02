import subprocess
import tempfile
import threading
import time
from typing import List, Optional, Tuple

from gpuhunt import KNOWN_NVIDIA_GPUS, AcceleratorVendor
from kubernetes import client

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithFilteredOffersCached,
    ComputeWithGatewaySupport,
    ComputeWithMultinodeSupport,
    ComputeWithPrivilegedSupport,
    generate_unique_gateway_instance_name,
    generate_unique_instance_name_for_job,
    get_docker_commands,
    get_dstack_gateway_commands,
    normalize_arch,
)
from dstack._internal.core.backends.base.offers import filter_offers_by_requirements
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesConfig,
    KubernetesProxyJumpConfig,
)
from dstack._internal.core.backends.kubernetes.utils import (
    call_api_method,
    get_api_from_config_data,
    get_cluster_public_ip,
    get_value,
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
from dstack._internal.core.models.resources import CPUSpec, Memory
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.common import parse_memory
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

JUMP_POD_SSH_PORT = 22

NVIDIA_GPU_NAME_TO_GPU_INFO = {gpu.name: gpu for gpu in KNOWN_NVIDIA_GPUS}
NVIDIA_GPU_NAMES = NVIDIA_GPU_NAME_TO_GPU_INFO.keys()

DUMMY_REGION = "-"


class KubernetesCompute(
    ComputeWithFilteredOffersCached,
    ComputeWithPrivilegedSupport,
    ComputeWithGatewaySupport,
    ComputeWithMultinodeSupport,
    Compute,
):
    def __init__(self, config: KubernetesConfig):
        super().__init__()
        self.config = config.copy()
        proxy_jump = self.config.proxy_jump
        if proxy_jump is None:
            proxy_jump = KubernetesProxyJumpConfig()
        self.proxy_jump = proxy_jump
        self.api = get_api_from_config_data(config.kubeconfig.data)

    def get_offers_by_requirements(
        self, requirements: Requirements
    ) -> List[InstanceOfferWithAvailability]:
        instance_offers: list[InstanceOfferWithAvailability] = []
        node_list = call_api_method(
            self.api.list_node,
            client.V1NodeList,
        )
        nodes = get_value(node_list, ".items", list[client.V1Node], required=True)
        for node in nodes:
            try:
                labels = get_value(node, ".metadata.labels", dict[str, str]) or {}
                name = get_value(node, ".metadata.name", str, required=True)
                cpus = _parse_cpu(
                    get_value(node, ".status.allocatable['cpu']", str, required=True)
                )
                cpu_arch = normalize_arch(
                    get_value(node, ".status.node_info.architecture", str)
                ).to_cpu_architecture()
                memory_mib = _parse_memory(
                    get_value(node, ".status.allocatable['memory']", str, required=True)
                )
                gpus, _ = _get_gpus_from_node_labels(labels)
                disk_size_mib = _parse_memory(
                    get_value(node, ".status.allocatable['ephemeral-storage']", str, required=True)
                )
            except (AttributeError, KeyError, ValueError) as e:
                logger.exception("Failed to process node: %s: %s", type(e).__name__, e)
                continue
            instance_offer = InstanceOfferWithAvailability(
                backend=BackendType.KUBERNETES,
                instance=InstanceType(
                    name=name,
                    resources=Resources(
                        cpus=cpus,
                        cpu_arch=cpu_arch,
                        memory_mib=memory_mib,
                        gpus=gpus,
                        spot=False,
                        disk=Disk(size_mib=disk_size_mib),
                    ),
                ),
                price=0,
                region=DUMMY_REGION,
                availability=InstanceAvailability.AVAILABLE,
                instance_runtime=InstanceRuntime.RUNNER,
            )
            instance_offers.extend(filter_offers_by_requirements([instance_offer], requirements))
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
        jump_pod_hostname = self.proxy_jump.hostname
        if jump_pod_hostname is None:
            jump_pod_hostname = get_cluster_public_ip(self.api)
            if jump_pod_hostname is None:
                raise ComputeError(
                    "Failed to acquire an IP for jump pod automatically. "
                    "Specify ssh_host for Kubernetes backend."
                )
        jump_pod_port, created = _create_jump_pod_service_if_not_exists(
            api=self.api,
            namespace=self.config.namespace,
            project_name=run.project_name,
            ssh_public_keys=[project_ssh_public_key.strip(), run.run_spec.ssh_key_pub.strip()],
            jump_pod_port=self.proxy_jump.port,
        )
        if not created:
            threading.Thread(
                target=_continue_setup_jump_pod,
                kwargs={
                    "api": self.api,
                    "namespace": self.config.namespace,
                    "project_name": run.project_name,
                    "project_ssh_private_key": project_ssh_private_key.strip(),
                    "user_ssh_public_key": run.run_spec.ssh_key_pub.strip(),
                    "jump_pod_host": jump_pod_hostname,
                    "jump_pod_port": jump_pod_port,
                },
            ).start()

        resources_requests: dict[str, str] = {}
        resources_limits: dict[str, str] = {}
        node_affinity: Optional[client.V1NodeAffinity] = None
        volumes_: list[client.V1Volume] = []
        volume_mounts: list[client.V1VolumeMount] = []

        resources_spec = job.job_spec.requirements.resources
        assert isinstance(resources_spec.cpu, CPUSpec)
        if (cpu_min := resources_spec.cpu.count.min) is not None:
            resources_requests["cpu"] = str(cpu_min)
        if (gpu_spec := resources_spec.gpu) is not None:
            gpu_min = gpu_spec.count.min
            if gpu_min is not None and gpu_min > 0:
                if not (offer_gpus := instance_offer.instance.resources.gpus):
                    raise ComputeError(
                        "GPU is requested but the offer has no GPUs:"
                        f" {gpu_spec=} {instance_offer=}",
                    )
                offer_gpu = offer_gpus[0]
                matching_gpu_label_values: set[str] = set()
                # We cannot generate an expected GPU label value from the Gpu model instance
                # as the actual values may have additional components (socket, memory type, etc.)
                # that we don't preserve in the Gpu model, e.g., "NVIDIA-H100-80GB-HBM3".
                # Moreover, a single Gpu may match multiple label values.
                # As a workaround, we iterate and process all node labels once again (we already
                # processed them in `get_offers_by_requirements()`).
                node_list = call_api_method(
                    self.api.list_node,
                    client.V1NodeList,
                )
                nodes = get_value(node_list, ".items", list[client.V1Node], required=True)
                for node in nodes:
                    labels = get_value(node, ".metadata.labels", dict[str, str])
                    if not labels:
                        continue
                    gpus, gpu_label_value = _get_gpus_from_node_labels(labels)
                    if not gpus or gpu_label_value is None:
                        continue
                    if gpus[0] == offer_gpu:
                        matching_gpu_label_values.add(gpu_label_value)
                if not matching_gpu_label_values:
                    raise ComputeError(
                        f"GPU is requested but no matching GPU labels found: {gpu_spec=}"
                    )
                logger.debug(
                    "Requesting %d GPU(s), node labels: %s", gpu_min, matching_gpu_label_values
                )
                # TODO: support other GPU vendors
                resources_requests["nvidia.com/gpu"] = str(gpu_min)
                resources_limits["nvidia.com/gpu"] = str(gpu_min)
                node_affinity = client.V1NodeAffinity(
                    required_during_scheduling_ignored_during_execution=[
                        client.V1NodeSelectorTerm(
                            match_expressions=[
                                client.V1NodeSelectorRequirement(
                                    key="nvidia.com/gpu.product",
                                    operator="In",
                                    values=list(matching_gpu_label_values),
                                ),
                            ],
                        ),
                    ],
                )

        if (memory_min := resources_spec.memory.min) is not None:
            resources_requests["memory"] = _render_memory(memory_min)
        if (
            resources_spec.disk is not None
            and (disk_min := resources_spec.disk.size.min) is not None
        ):
            resources_requests["ephemeral-storage"] = _render_memory(disk_min)
        if (shm_size := resources_spec.shm_size) is not None:
            shm_volume_name = "dev-shm"
            volumes_.append(
                client.V1Volume(
                    name=shm_volume_name,
                    empty_dir=client.V1EmptyDirVolumeSource(
                        medium="Memory",
                        size_limit=_render_memory(shm_size),
                    ),
                )
            )
            volume_mounts.append(
                client.V1VolumeMount(
                    name=shm_volume_name,
                    mount_path="/dev/shm",
                )
            )

        pod = client.V1Pod(
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
                            privileged=job.job_spec.privileged,
                            capabilities=client.V1Capabilities(
                                add=[
                                    # Allow to increase hard resource limits, see getrlimit(2)
                                    "SYS_RESOURCE",
                                ],
                            ),
                        ),
                        resources=client.V1ResourceRequirements(
                            requests=resources_requests,
                            limits=resources_limits,
                        ),
                        volume_mounts=volume_mounts,
                    )
                ],
                affinity=node_affinity,
                volumes=volumes_,
            ),
        )
        call_api_method(
            self.api.create_namespaced_pod,
            client.V1Pod,
            namespace=self.config.namespace,
            body=pod,
        )
        call_api_method(
            self.api.create_namespaced_service,
            client.V1Service,
            namespace=self.config.namespace,
            body=client.V1Service(
                metadata=client.V1ObjectMeta(name=_get_pod_service_name(instance_name)),
                spec=client.V1ServiceSpec(
                    type="ClusterIP",
                    selector={"app.kubernetes.io/name": instance_name},
                    ports=[client.V1ServicePort(port=DSTACK_RUNNER_SSH_PORT)],
                ),
            ),
        )
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_name,
            # Although we can already get Service's ClusterIP from the `V1Service` object returned
            # by the `create_namespaced_service` method, we still need PodIP for multinode runs.
            # We'll update both hostname and internal_ip once the pod is assigned to the node.
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
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

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        pod = call_api_method(
            self.api.read_namespaced_pod,
            client.V1Pod,
            name=provisioning_data.instance_id,
            namespace=self.config.namespace,
        )
        pod_ip = get_value(pod, ".status.pod_ip", str)
        if not pod_ip:
            return
        provisioning_data.internal_ip = pod_ip
        service = call_api_method(
            self.api.read_namespaced_service,
            client.V1Service,
            name=_get_pod_service_name(provisioning_data.instance_id),
            namespace=self.config.namespace,
        )
        provisioning_data.hostname = get_value(service, ".spec.cluster_ip", str, required=True)

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        call_api_method(
            self.api.delete_namespaced_service,
            client.V1Service,
            expected=404,
            name=_get_pod_service_name(instance_id),
            namespace=self.config.namespace,
            body=client.V1DeleteOptions(),
        )
        call_api_method(
            self.api.delete_namespaced_pod,
            client.V1Pod,
            expected=404,
            name=instance_id,
            namespace=self.config.namespace,
            body=client.V1DeleteOptions(),
        )

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
        pod = client.V1Pod(
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
        )
        call_api_method(
            self.api.create_namespaced_pod,
            client.V1Pod,
            namespace=self.config.namespace,
            body=pod,
        )
        service = client.V1Service(
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
        )
        call_api_method(
            self.api.create_namespaced_service,
            client.V1Service,
            namespace=self.config.namespace,
            body=service,
        )
        hostname = _wait_for_load_balancer_hostname(
            api=self.api,
            namespace=self.config.namespace,
            service_name=_get_pod_service_name(instance_name),
        )
        region = DUMMY_REGION
        if hostname is None:
            self.terminate_instance(instance_name, region=region)
            raise ComputeError(
                "Failed to get gateway hostname. "
                "Ensure the Kubernetes cluster supports Load Balancer services."
            )
        return GatewayProvisioningData(
            instance_id=instance_name,
            ip_address=hostname,
            region=region,
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


def _parse_cpu(cpu: str) -> int:
    if cpu.endswith("m"):
        # "m" means millicpu (1/1000 CPU), e.g., 7900m -> 7.9 -> 7
        return int(float(cpu[:-1]) / 1000)
    return int(cpu)


def _parse_memory(memory: str) -> int:
    if memory.isdigit():
        # no suffix means that the value is in bytes
        return int(memory) // 2**20
    return int(parse_memory(memory, as_untis="M"))


def _render_memory(memory: Memory) -> str:
    return f"{float(memory)}Gi"


def _get_gpus_from_node_labels(labels: dict[str, str]) -> tuple[list[Gpu], Optional[str]]:
    # We rely on https://github.com/NVIDIA/k8s-device-plugin/tree/main/docs/gpu-feature-discovery
    # to detect gpus. Note that "nvidia.com/gpu.product" is not a short gpu name like "T4" or
    # "A100" but a product name like "Tesla-T4" or "A100-SXM4-40GB".
    # Thus, we convert the product name to a known gpu name.
    # TODO: support other GPU vendors
    gpu_count = labels.get("nvidia.com/gpu.count")
    gpu_product = labels.get("nvidia.com/gpu.product")
    if gpu_count is None or gpu_product is None:
        return [], None
    gpu_count = int(gpu_count)
    gpu_name = None
    for known_gpu_name in NVIDIA_GPU_NAMES:
        if known_gpu_name.lower() in gpu_product.lower().split("-"):
            gpu_name = known_gpu_name
            break
    if gpu_name is None:
        return [], None
    gpu_info = NVIDIA_GPU_NAME_TO_GPU_INFO[gpu_name]
    gpu_memory = gpu_info.memory * 1024
    # A100 may come in two variants
    if "40GB" in gpu_product:
        gpu_memory = 40 * 1024
    gpus = [
        Gpu(vendor=AcceleratorVendor.NVIDIA, name=gpu_name, memory_mib=gpu_memory)
        for _ in range(gpu_count)
    ]
    return gpus, gpu_product


def _continue_setup_jump_pod(
    api: client.CoreV1Api,
    namespace: str,
    project_name: str,
    project_ssh_private_key: str,
    user_ssh_public_key: str,
    jump_pod_host: str,
    jump_pod_port: int,
):
    _wait_for_pod_ready(
        api=api,
        namespace=namespace,
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
    namespace: str,
    project_name: str,
    ssh_public_keys: List[str],
    jump_pod_port: Optional[int],
) -> Tuple[int, bool]:
    created = False
    service: Optional[client.V1Service] = None
    pod: Optional[client.V1Pod] = None
    _namespace = call_api_method(
        api.read_namespace,
        client.V1Namespace,
        expected=404,
        name=namespace,
    )
    if _namespace is None:
        _namespace = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=namespace,
                labels={"app.kubernetes.io/name": namespace},
            ),
        )
        call_api_method(
            api.create_namespace,
            client.V1Namespace,
            body=_namespace,
        )
    else:
        service = call_api_method(
            api.read_namespaced_service,
            client.V1Service,
            expected=404,
            name=_get_jump_pod_service_name(project_name),
            namespace=namespace,
        )
        pod = call_api_method(
            api.read_namespaced_pod,
            client.V1Pod,
            expected=404,
            name=_get_jump_pod_name(project_name),
            namespace=namespace,
        )
    # The service may exist without the pod if the node on which the jump pod was running
    # has been deleted.
    if service is None or pod is None:
        service = _create_jump_pod_service(
            api=api,
            namespace=namespace,
            project_name=project_name,
            ssh_public_keys=ssh_public_keys,
            jump_pod_port=jump_pod_port,
        )
        created = True
    port = get_value(service, ".spec.ports[0].node_port", int, required=True)
    return port, created


def _create_jump_pod_service(
    api: client.CoreV1Api,
    namespace: str,
    project_name: str,
    ssh_public_keys: List[str],
    jump_pod_port: Optional[int],
) -> client.V1Service:
    # TODO use restricted ssh-forwarding-only user for jump pod instead of root.
    pod_name = _get_jump_pod_name(project_name)
    call_api_method(
        api.delete_namespaced_pod,
        client.V1Pod,
        expected=404,
        namespace=namespace,
        name=pod_name,
    )
    commands = _get_jump_pod_commands(authorized_keys=ssh_public_keys)
    pod = client.V1Pod(
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
    )
    call_api_method(
        api.create_namespaced_pod,
        client.V1Pod,
        namespace=namespace,
        body=pod,
    )
    service_name = _get_jump_pod_service_name(project_name)
    call_api_method(
        api.delete_namespaced_service,
        client.V1Service,
        expected=404,
        namespace=namespace,
        name=service_name,
    )
    service = client.V1Service(
        metadata=client.V1ObjectMeta(name=service_name),
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
    )
    return call_api_method(
        api.create_namespaced_service,
        client.V1Service,
        namespace=namespace,
        body=service,
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
    namespace: str,
    pod_name: str,
    timeout_seconds: int = 300,
):
    start_time = time.time()
    while True:
        pod = call_api_method(
            api.read_namespaced_pod,
            client.V1Pod,
            expected=404,
            name=pod_name,
            namespace=namespace,
        )
        if pod is not None:
            phase = get_value(pod, ".status.phase", str, required=True)
            container_statuses = get_value(
                pod, ".status.container_statuses", list[client.V1ContainerStatus], required=True
            )
            if phase == "Running" and all(status.ready for status in container_statuses):
                return True
        elapsed_time = time.time() - start_time
        if elapsed_time >= timeout_seconds:
            logger.warning("Timeout waiting for pod %s to be ready", pod_name)
            return False
        time.sleep(1)


def _wait_for_load_balancer_hostname(
    api: client.CoreV1Api,
    namespace: str,
    service_name: str,
    timeout_seconds: int = 120,
) -> Optional[str]:
    start_time = time.time()
    while True:
        service = call_api_method(
            api.read_namespaced_service,
            client.V1Service,
            expected=404,
            name=service_name,
            namespace=namespace,
        )
        if service is not None:
            hostname = get_value(service, ".status.load_balancer.ingress[0].hostname", str)
            if hostname is not None:
                return hostname
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
    return f"dstack-{project_name}-ssh-jump-pod"


def _get_jump_pod_service_name(project_name: str) -> str:
    return f"dstack-{project_name}-ssh-jump-pod-service"


def _get_pod_service_name(pod_name: str) -> str:
    return f"{pod_name}-service"
