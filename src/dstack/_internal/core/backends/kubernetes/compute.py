import shlex
import subprocess
import tempfile
import threading
import time
from enum import Enum
from typing import List, Optional

from gpuhunt import KNOWN_AMD_GPUS, KNOWN_NVIDIA_GPUS, AcceleratorVendor
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
)
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType
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
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.resources import CPUSpec, GPUSpec, Memory
from dstack._internal.core.models.routers import AnyRouterConfig
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.common import get_or_error, parse_memory
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

JUMP_POD_IMAGE = "testcontainers/sshd:1.3.0@sha256:c50c0f59554dcdb2d9e5e705112144428ae9d04ac0af6322b365a18e24213a6a"
JUMP_POD_SSH_PORT = 22
DUMMY_REGION = "-"

NVIDIA_GPU_RESOURCE = "nvidia.com/gpu"
NVIDIA_GPU_NODE_TAINT = NVIDIA_GPU_RESOURCE
NVIDIA_GPU_PRODUCT_LABEL = f"{NVIDIA_GPU_RESOURCE}.product"

AMD_GPU_RESOURCE = "amd.com/gpu"
AMD_GPU_NODE_TAINT = AMD_GPU_RESOURCE
# The oldest but still supported label format, the safest option, see the commit message:
# https://github.com/ROCm/k8s-device-plugin/commit/c0b0231b391a56bc9da4f362d561e25e960d7a48
# E.g., beta.amd.com/gpu.device-id.74b5=4 - A node with four MI300X VF (0x74b5) GPUs
# We cannot rely on the beta.amd.com/gpu.product-name.* label, as it may be missing, see the issue:
# https://github.com/ROCm/k8s-device-plugin/issues/112
AMD_GPU_DEVICE_ID_LABEL_PREFIX = f"beta.{AMD_GPU_RESOURCE}.device-id."

# Taints we know and tolerate when creating our objects, e.g., the jump pod.
TOLERATED_NODE_TAINTS = (NVIDIA_GPU_NODE_TAINT, AMD_GPU_NODE_TAINT)

NVIDIA_GPU_NAME_TO_GPU_INFO = {gpu.name: gpu for gpu in KNOWN_NVIDIA_GPUS}
NVIDIA_GPU_NAMES = NVIDIA_GPU_NAME_TO_GPU_INFO.keys()

AMD_GPU_DEVICE_ID_TO_GPU_INFO = {
    device_id: gpu_info for gpu_info in KNOWN_AMD_GPUS for device_id in gpu_info.device_ids
}
AMD_GPU_NAME_TO_DEVICE_IDS = {gpu.name: gpu.device_ids for gpu in KNOWN_AMD_GPUS}


class Operator(str, Enum):
    EXISTS = "Exists"
    IN = "In"


class TaintEffect(str, Enum):
    NO_EXECUTE = "NoExecute"
    NO_SCHEDULE = "NoSchedule"
    PREFER_NO_SCHEDULE = "PreferNoSchedule"


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
    ) -> list[InstanceOfferWithAvailability]:
        instance_offers: list[InstanceOfferWithAvailability] = []
        for node in self.api.list_node().items:
            if (instance_offer := _get_instance_offer_from_node(node)) is not None:
                instance_offers.extend(
                    filter_offers_by_requirements([instance_offer], requirements)
                )
        return instance_offers

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: list[Volume],
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name_for_job(run, job)
        assert run.run_spec.ssh_key_pub is not None
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
        tolerations: list[client.V1Toleration] = []
        volumes_: list[client.V1Volume] = []
        volume_mounts: list[client.V1VolumeMount] = []

        resources_spec = job.job_spec.requirements.resources
        assert isinstance(resources_spec.cpu, CPUSpec)
        if (cpu_min := resources_spec.cpu.count.min) is not None:
            resources_requests["cpu"] = str(cpu_min)
        if (cpu_max := resources_spec.cpu.count.max) is not None:
            resources_limits["cpu"] = str(cpu_max)
        if (gpu_spec := resources_spec.gpu) is not None:
            gpu_min = gpu_spec.count.min
            if gpu_min is not None and gpu_min > 0:
                gpu_resource, node_affinity, node_taint = _get_pod_spec_parameters_for_gpu(
                    self.api, gpu_spec
                )
                logger.debug("Requesting GPU resource: %s=%d", gpu_resource, gpu_min)
                # Limit must be set (GPU resources cannot be overcommitted)
                # and must be equal to request.
                resources_requests[gpu_resource] = resources_limits[gpu_resource] = str(gpu_min)
                # It should be NoSchedule, but we also add NoExecute toleration just in case.
                for effect in [TaintEffect.NO_SCHEDULE, TaintEffect.NO_EXECUTE]:
                    tolerations.append(
                        client.V1Toleration(
                            key=node_taint, operator=Operator.EXISTS, effect=effect
                        )
                    )
        if (memory_min := resources_spec.memory.min) is not None:
            resources_requests["memory"] = _render_memory(memory_min)
        if (memory_max := resources_spec.memory.max) is not None:
            resources_limits["memory"] = _render_memory(memory_max)
        if (disk_spec := resources_spec.disk) is not None:
            if (disk_min := disk_spec.size.min) is not None:
                resources_requests["ephemeral-storage"] = _render_memory(disk_min)
            if (disk_max := disk_spec.size.max) is not None:
                resources_limits["ephemeral-storage"] = _render_memory(disk_max)
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
                affinity=client.V1Affinity(
                    node_affinity=node_affinity,
                ),
                tolerations=tolerations,
                volumes=volumes_,
            ),
        )
        self.api.create_namespaced_pod(
            namespace=self.config.namespace,
            body=pod,
        )
        self.api.create_namespaced_service(
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
            # by the `create_namespaced_service` method, we still need 1) updated instance offer
            # 2) PodIP for multinode runs.
            # We'll update all these fields once the pod is assigned to the node.
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
        pod = self.api.read_namespaced_pod(
            name=provisioning_data.instance_id,
            namespace=self.config.namespace,
        )
        if pod.status is None:
            return
        pod_ip = pod.status.pod_ip
        if not pod_ip:
            return
        provisioning_data.internal_ip = pod_ip
        service = self.api.read_namespaced_service(
            name=_get_pod_service_name(provisioning_data.instance_id),
            namespace=self.config.namespace,
        )
        service_spec = get_or_error(service.spec)
        provisioning_data.hostname = get_or_error(service_spec.cluster_ip)
        pod_spec = get_or_error(pod.spec)
        node = self.api.read_node(name=get_or_error(pod_spec.node_name))
        if (instance_offer := _get_instance_offer_from_node(node)) is not None:
            provisioning_data.instance_type = instance_offer.instance
            provisioning_data.region = instance_offer.region
            provisioning_data.price = instance_offer.price

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        call_api_method(
            self.api.delete_namespaced_service,
            expected=404,
            name=_get_pod_service_name(instance_id),
            namespace=self.config.namespace,
            body=client.V1DeleteOptions(),
        )
        call_api_method(
            self.api.delete_namespaced_pod,
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

        # TODO: By default EKS creates a Classic Load Balancer for Load Balancer services.
        # Consider deploying an NLB. It seems it requires some extra configuration on the cluster:
        # https://docs.aws.amazon.com/eks/latest/userguide/network-load-balancing.html
        if configuration.instance_type is not None:
            raise ComputeError(
                "The `kubernetes` backend does not support the `instance_type`"
                " gateway configuration property"
            )
        instance_name = generate_unique_gateway_instance_name(configuration)
        commands = _get_gateway_commands(
            authorized_keys=[configuration.ssh_key_pub], router=configuration.router
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
                        security_context=client.V1SecurityContext(
                            run_as_user=0,
                            run_as_group=0,
                        ),
                    )
                ]
            ),
        )
        self.api.create_namespaced_pod(
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
        self.api.create_namespaced_service(
            namespace=self.config.namespace,
            body=service,
        )
        # address is eiher a domain name or an IP address
        address = _wait_for_load_balancer_address(
            api=self.api,
            namespace=self.config.namespace,
            service_name=_get_pod_service_name(instance_name),
        )
        region = DUMMY_REGION
        if address is None:
            self.terminate_instance(instance_name, region=region)
            raise ComputeError(
                "Failed to get gateway hostname. "
                "Ensure the Kubernetes cluster supports Load Balancer services."
            )
        return GatewayProvisioningData(
            instance_id=instance_name,
            ip_address=address,
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


def _get_instance_offer_from_node(node: client.V1Node) -> Optional[InstanceOfferWithAvailability]:
    try:
        node_name = get_or_error(get_or_error(node.metadata).name)
        node_status = get_or_error(node.status)
        allocatable = get_or_error(node_status.allocatable)
        _cpu_arch: Optional[str] = None
        if node_status.node_info is not None:
            _cpu_arch = node_status.node_info.architecture
        cpu_arch = normalize_arch(_cpu_arch).to_cpu_architecture()
        cpus = _parse_cpu(allocatable["cpu"])
        memory_mib = _parse_memory(allocatable["memory"])
        disk_size_mib = _parse_memory(allocatable["ephemeral-storage"])
        gpus = _get_node_gpus(node)
    except (ValueError, KeyError) as e:
        logger.exception("Failed to process node: %s: %s", type(e).__name__, e)
        return None
    return InstanceOfferWithAvailability(
        backend=BackendType.KUBERNETES,
        instance=InstanceType(
            name=node_name,
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


def _get_node_labels(node: client.V1Node) -> dict[str, str]:
    if (metadata := node.metadata) is None:
        return {}
    if (labels := metadata.labels) is None:
        return {}
    return labels


def _get_node_gpus(node: client.V1Node) -> list[Gpu]:
    node_name = get_or_error(get_or_error(node.metadata).name)
    allocatable = get_or_error(get_or_error(node.status).allocatable)
    labels = _get_node_labels(node)
    for gpu_resource, gpu_getter in (
        (NVIDIA_GPU_RESOURCE, _get_nvidia_gpu_from_node_labels),
        (AMD_GPU_RESOURCE, _get_amd_gpu_from_node_labels),
    ):
        _gpu_count = allocatable.get(gpu_resource)
        if not _gpu_count:
            continue
        gpu_count = int(_gpu_count)
        if gpu_count < 1:
            continue
        gpu = gpu_getter(labels)
        if gpu is None:
            logger.warning(
                "Node %s: GPU resource found, but failed to detect its model: %s=%d",
                node_name,
                gpu_resource,
                gpu_count,
            )
            return []
        return [gpu] * gpu_count
    logger.debug("Node %s: no GPU resource found", node_name)
    return []


def _get_nvidia_gpu_from_node_labels(labels: dict[str, str]) -> Optional[Gpu]:
    # We rely on https://github.com/NVIDIA/k8s-device-plugin/tree/main/docs/gpu-feature-discovery
    # to detect gpus. Note that "nvidia.com/gpu.product" is not a short gpu name like "T4" or
    # "A100" but a product name like "Tesla-T4" or "A100-SXM4-40GB".
    # Thus, we convert the product name to a known gpu name.
    gpu_product = labels.get(NVIDIA_GPU_PRODUCT_LABEL)
    if gpu_product is None:
        return None
    for gpu_name in NVIDIA_GPU_NAMES:
        if gpu_name.lower() in gpu_product.lower().split("-"):
            break
    else:
        return None
    gpu_info = NVIDIA_GPU_NAME_TO_GPU_INFO[gpu_name]
    gpu_memory = gpu_info.memory * 1024
    # A100 may come in two variants
    if "40GB" in gpu_product:
        gpu_memory = 40 * 1024
    return Gpu(vendor=AcceleratorVendor.NVIDIA, name=gpu_name, memory_mib=gpu_memory)


def _get_amd_gpu_from_node_labels(labels: dict[str, str]) -> Optional[Gpu]:
    # (AMDGPUInfo.name, AMDGPUInfo.memory) pairs
    gpus: set[tuple[str, int]] = set()
    for label in labels:
        if not label.startswith(AMD_GPU_DEVICE_ID_LABEL_PREFIX):
            continue
        _, _, _device_id = label.rpartition(".")
        device_id = int(_device_id, 16)
        gpu_info = AMD_GPU_DEVICE_ID_TO_GPU_INFO.get(device_id)
        if gpu_info is None:
            logger.warning("Unknown AMD GPU device id: %X", device_id)
            continue
        gpus.add((gpu_info.name, gpu_info.memory))
    if not gpus:
        return None
    if len(gpus) == 1:
        gpu_name, gpu_memory_gib = next(iter(gpus))
        return Gpu(vendor=AcceleratorVendor.AMD, name=gpu_name, memory_mib=gpu_memory_gib * 1024)
    logger.warning("Multiple AMD GPU models detected: %s, ignoring all GPUs", gpus)
    return None


def _get_pod_spec_parameters_for_gpu(
    api: client.CoreV1Api, gpu_spec: GPUSpec
) -> tuple[str, client.V1NodeAffinity, str]:
    nodes = api.list_node().items
    gpu_vendor = gpu_spec.vendor
    # If no vendor specified, we assume it's NVIDIA. Technically, it's possible to request either
    # NVIDIA or AMD in the run configuration using only GPU names (e.g.,`gpu: H100,MI300X:8`),
    # but we ignore such configurations as it's hard to translate them to K8s request.
    if gpu_vendor is None or gpu_vendor == AcceleratorVendor.NVIDIA:
        node_affinity = _get_nvidia_gpu_node_affinity(gpu_spec, nodes)
        return NVIDIA_GPU_RESOURCE, node_affinity, NVIDIA_GPU_NODE_TAINT
    if gpu_vendor == AcceleratorVendor.AMD:
        node_affinity = _get_amd_gpu_node_affinity(gpu_spec, nodes)
        return AMD_GPU_RESOURCE, node_affinity, AMD_GPU_NODE_TAINT
    raise ComputeError(f"Unsupported GPU vendor: {gpu_vendor}")


def _get_nvidia_gpu_node_affinity(
    gpu_spec: GPUSpec, nodes: list[client.V1Node]
) -> client.V1NodeAffinity:
    matching_gpu_label_values: set[str] = set()
    for node in nodes:
        labels = _get_node_labels(node)
        gpu = _get_nvidia_gpu_from_node_labels(labels)
        if gpu is not None and _gpu_matches_gpu_spec(gpu, gpu_spec):
            matching_gpu_label_values.add(labels[NVIDIA_GPU_PRODUCT_LABEL])
    if not matching_gpu_label_values:
        raise ComputeError(
            f"NVIDIA GPU is requested but no matching GPU labels found: {gpu_spec=}"
        )
    logger.debug(
        "Selecting nodes by labels %s for NVIDIA %s", matching_gpu_label_values, gpu_spec.name
    )
    return client.V1NodeAffinity(
        required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
            node_selector_terms=[
                client.V1NodeSelectorTerm(
                    match_expressions=[
                        client.V1NodeSelectorRequirement(
                            key=NVIDIA_GPU_PRODUCT_LABEL,
                            operator=Operator.IN,
                            values=list(matching_gpu_label_values),
                        ),
                    ],
                ),
            ],
        ),
    )


def _get_amd_gpu_node_affinity(
    gpu_spec: GPUSpec, nodes: list[client.V1Node]
) -> client.V1NodeAffinity:
    matching_device_ids: set[int] = set()
    for node in nodes:
        labels = _get_node_labels(node)
        gpu = _get_amd_gpu_from_node_labels(labels)
        if gpu is not None and _gpu_matches_gpu_spec(gpu, gpu_spec):
            matching_device_ids.update(AMD_GPU_NAME_TO_DEVICE_IDS[gpu.name])
    return client.V1NodeAffinity(
        required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
            node_selector_terms=[
                client.V1NodeSelectorTerm(
                    match_expressions=[
                        client.V1NodeSelectorRequirement(
                            key=f"{AMD_GPU_DEVICE_ID_LABEL_PREFIX}{device_id:x}",
                            operator=Operator.EXISTS,
                        ),
                    ],
                )
                for device_id in matching_device_ids
            ],
        ),
    )


def _gpu_matches_gpu_spec(gpu: Gpu, gpu_spec: GPUSpec) -> bool:
    if gpu_spec.vendor is not None and gpu.vendor != gpu_spec.vendor:
        return False
    if gpu_spec.name is not None and gpu.name.lower() not in map(str.lower, gpu_spec.name):
        return False
    if gpu_spec.memory is not None:
        min_memory_gib = gpu_spec.memory.min
        if min_memory_gib is not None and gpu.memory_mib < min_memory_gib * 1024:
            return False
        max_memory_gib = gpu_spec.memory.max
        if max_memory_gib is not None and gpu.memory_mib > max_memory_gib * 1024:
            return False
    if gpu_spec.compute_capability is not None:
        if gpu.vendor != AcceleratorVendor.NVIDIA:
            return False
        gpu_info = NVIDIA_GPU_NAME_TO_GPU_INFO.get(gpu.name)
        if gpu_info is None:
            return False
        if gpu_info.compute_capability < gpu_spec.compute_capability:
            return False
    return True


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
    ssh_public_keys: list[str],
    jump_pod_port: Optional[int],
) -> tuple[int, bool]:
    created = False
    service: Optional[client.V1Service] = None
    pod: Optional[client.V1Pod] = None
    _namespace = call_api_method(
        api.read_namespace,
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
        api.create_namespace(body=_namespace)
    else:
        service = call_api_method(
            api.read_namespaced_service,
            expected=404,
            name=_get_jump_pod_service_name(project_name),
            namespace=namespace,
        )
        pod = call_api_method(
            api.read_namespaced_pod,
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
    port: Optional[int] = None
    if service.spec is not None and service.spec.ports:
        port = service.spec.ports[0].node_port
    if port is None:
        raise ComputeError(
            f"Failed to get NodePort of jump pod Service for project '{project_name}'"
        )
    return port, created


def _create_jump_pod_service(
    api: client.CoreV1Api,
    namespace: str,
    project_name: str,
    ssh_public_keys: list[str],
    jump_pod_port: Optional[int],
) -> client.V1Service:
    # TODO use restricted ssh-forwarding-only user for jump pod instead of root.
    pod_name = _get_jump_pod_name(project_name)
    call_api_method(
        api.delete_namespaced_pod,
        expected=404,
        namespace=namespace,
        name=pod_name,
    )

    # False if we found at least one node without any "hard" taint, that is, if we don't need to
    # specify the toleration.
    toleration_required = True
    # (key, effect) pairs.
    tolerated_taints: set[tuple[str, str]] = set()
    for node in api.list_node().items:
        if (node_spec := node.spec) is None:
            continue
        # True if the node has at least one NoExecute or NoSchedule taint.
        has_hard_taint = False
        taints = node_spec.taints or []
        for taint in taints:
            # A "soft" taint, ignore.
            if taint.effect == TaintEffect.PREFER_NO_SCHEDULE:
                continue
            has_hard_taint = True
            if taint.key in TOLERATED_NODE_TAINTS:
                tolerated_taints.add((taint.key, taint.effect))
        if not has_hard_taint:
            toleration_required = False
            break
    tolerations: list[client.V1Toleration] = []
    if toleration_required:
        for key, effect in tolerated_taints:
            tolerations.append(
                client.V1Toleration(key=key, operator=Operator.EXISTS, effect=effect)
            )
        if not tolerations:
            logger.warning("No appropriate node found, the jump pod may never be scheduled")

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
                    image=JUMP_POD_IMAGE,
                    command=["/bin/sh"],
                    args=["-c", " && ".join(commands)],
                    ports=[
                        client.V1ContainerPort(
                            container_port=JUMP_POD_SSH_PORT,
                        )
                    ],
                )
            ],
            tolerations=tolerations,
        ),
    )
    api.create_namespaced_pod(
        namespace=namespace,
        body=pod,
    )
    service_name = _get_jump_pod_service_name(project_name)
    call_api_method(
        api.delete_namespaced_service,
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
    return api.create_namespaced_service(
        namespace=namespace,
        body=service,
    )


def _get_jump_pod_commands(authorized_keys: list[str]) -> list[str]:
    authorized_keys_content = "\n".join(authorized_keys).strip()
    commands = [
        "mkdir -p ~/.ssh",
        "chmod 700 ~/.ssh",
        f"echo '{authorized_keys_content}' > ~/.ssh/authorized_keys",
        "chmod 600 ~/.ssh/authorized_keys",
        # regenerate host keys
        "rm -rf /etc/ssh/ssh_host_*",
        "ssh-keygen -A > /dev/null",
        # start sshd
        (
            f"/usr/sbin/sshd -D -e -p {JUMP_POD_SSH_PORT}"
            " -o LogLevel=ERROR"
            " -o PasswordAuthentication=no"
            " -o AllowTcpForwarding=local"
            # proxy jumping only, no shell access
            " -o ForceCommand=/bin/false"
        ),
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
            expected=404,
            name=pod_name,
            namespace=namespace,
        )
        if pod is not None:
            pod_status = get_or_error(pod.status)
            phase = get_or_error(pod_status.phase)
            container_statuses = get_or_error(pod_status.container_statuses)
            if phase == "Running" and all(status.ready for status in container_statuses):
                return True
        elapsed_time = time.time() - start_time
        if elapsed_time >= timeout_seconds:
            logger.warning("Timeout waiting for pod %s to be ready", pod_name)
            return False
        time.sleep(1)


def _wait_for_load_balancer_address(
    api: client.CoreV1Api,
    namespace: str,
    service_name: str,
    timeout_seconds: int = 120,
) -> Optional[str]:
    start_time = time.time()
    while True:
        service = call_api_method(
            api.read_namespaced_service,
            expected=404,
            name=service_name,
            namespace=namespace,
        )
        if (
            service is not None
            and (service_status := service.status) is not None
            and (lb_status := service_status.load_balancer) is not None
            and (ingress_points := lb_status.ingress)
        ):
            ingress_point = ingress_points[0]
            # > Hostname is set for load-balancer ingress points that are DNS based (typically
            # > AWS load-balancers)
            # > IP is set for load-balancer ingress points that are IP based (typically GCE or
            # > OpenStack load-balancers)
            address = ingress_point.hostname or ingress_point.ip
            if address is not None:
                return address
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


def _get_gateway_commands(
    authorized_keys: List[str], router: Optional[AnyRouterConfig] = None
) -> List[str]:
    authorized_keys_content = "\n".join(authorized_keys).strip()
    gateway_commands = " && ".join(get_dstack_gateway_commands(router=router))
    quoted_gateway_commands = shlex.quote(gateway_commands)

    commands = [
        # install packages
        "apt-get update && apt-get install -y sudo wget openssh-server nginx python3.10-venv libaugeas0",
        # install docker-systemctl-replacement
        "wget https://raw.githubusercontent.com/gdraheim/docker-systemctl-replacement/b18d67e521f0d1cf1d705dbb8e0416bef23e377c/files/docker/systemctl3.py -O /usr/bin/systemctl",
        "chmod a+rx /usr/bin/systemctl",
        # install certbot
        "python3 -m venv /root/certbotvenv/",
        "/root/certbotvenv/bin/pip install certbot-nginx",
        "ln -s /root/certbotvenv/bin/certbot /usr/bin/certbot",
        # prohibit password authentication
        'sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config',
        # set up ubuntu user
        "useradd -mUG sudo ubuntu",
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
        f"su ubuntu -c {quoted_gateway_commands}",
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
