import dataclasses
from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from typing import Callable, Optional, Union, cast

from gpuhunt import KNOWN_AMD_GPUS, KNOWN_NVIDIA_GPUS, AcceleratorVendor

# XXX: kubernetes.utils is missing in the stubs package
from kubernetes import utils as _kubernetes_utils  # pyright: ignore[reportAttributeAccessIssue]
from kubernetes.client import CoreV1Api, V1Node, V1Taint
from typing_extensions import Self

from dstack._internal.core.backends.base.compute import normalize_arch
from dstack._internal.core.backends.base.offers import filter_offers_by_requirements
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import CPUSpec, GPUSpec, Memory
from dstack._internal.core.models.runs import Requirements
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

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

NVIDIA_GPU_NAME_TO_GPU_INFO = {gpu.name: gpu for gpu in KNOWN_NVIDIA_GPUS}
NVIDIA_GPU_NAMES = NVIDIA_GPU_NAME_TO_GPU_INFO.keys()

AMD_GPU_DEVICE_ID_TO_GPU_INFO = {
    device_id: gpu_info for gpu_info in KNOWN_AMD_GPUS for device_id in gpu_info.device_ids
}
AMD_GPU_NAME_TO_DEVICE_IDS = {gpu.name: gpu.device_ids for gpu in KNOWN_AMD_GPUS}


class PodPhase(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    UNKNOWN = "Unknown"  # Deprecated: It isn't being set since 2015

    def is_finished(self):
        return self in [self.SUCCEEDED, self.FAILED]

    def is_running(self):
        return self == self.RUNNING


class TaintEffect(str, Enum):
    NO_EXECUTE = "NoExecute"
    NO_SCHEDULE = "NoSchedule"
    PREFER_NO_SCHEDULE = "PreferNoSchedule"


class KubernetesResource(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    EPHEMERAL_STORAGE = "ephemeral-storage"
    NVIDIA_GPU = NVIDIA_GPU_RESOURCE
    AMD_GPU = AMD_GPU_RESOURCE


@dataclasses.dataclass
class KubernetesResources:
    cpu: Decimal = Decimal("0")
    memory: Decimal = Decimal("0")
    ephemeral_storage: Decimal = Decimal("0")
    nvidia_gpu: Decimal = Decimal("0")
    amd_gpu: Decimal = Decimal("0")

    @classmethod
    def from_kubernetes_map(cls, map_: Mapping[str, str]) -> Self:
        dct: dict[str, Decimal] = {}
        for resource in KubernetesResource:
            if (qty := map_.get(resource.value)) is not None:
                dct[resource.name.lower()] = parse_quantity(qty)
        return cls(**dct)

    def __getitem__(self, key: str) -> Decimal:
        try:
            resource = KubernetesResource(key)
        except ValueError:
            raise KeyError(key)
        return getattr(self, resource.name.lower())

    def __add__(self, other: Self) -> Self:
        dct: dict[str, Decimal] = dataclasses.asdict(self)
        qty: Decimal
        for field, qty in dataclasses.asdict(other).items():
            dct[field] += qty
        return type(self)(**dct)

    def __sub__(self, other: Self) -> Self:
        dct: dict[str, Decimal] = dataclasses.asdict(self)
        qty: Decimal
        for field, qty in dataclasses.asdict(other).items():
            dct[field] -= qty
        return type(self)(**dct)


parse_quantity = cast(
    Callable[[Union[str, int, float, Decimal]], Decimal], _kubernetes_utils.parse_quantity
)


def format_memory(memory: Memory) -> str:
    return f"{float(memory)}Gi"


def get_gpu_request_from_gpu_spec(gpu_spec: GPUSpec) -> int:
    return gpu_spec.count.min or 0


def get_node_name(node: V1Node) -> Optional[str]:
    if (metadata := node.metadata) is None:
        return None
    return metadata.name


def get_node_labels(node: V1Node) -> dict[str, str]:
    if (metadata := node.metadata) is None:
        return {}
    if (labels := metadata.labels) is None:
        return {}
    return labels


def is_hard_taint(taint: V1Taint) -> bool:
    if taint.effect == TaintEffect.PREFER_NO_SCHEDULE:
        return False
    if taint.effect not in TaintEffect:
        logger.warning(
            "Unexpected taint %s=%s effect: %s", taint.key, taint.value or "", taint.effect
        )
    return True


def is_taint_tolerated(taint: V1Taint) -> bool:
    return taint.key in (NVIDIA_GPU_NODE_TAINT, AMD_GPU_NODE_TAINT)


def get_instance_offers(
    api: CoreV1Api, requirements: Requirements
) -> list[InstanceOfferWithAvailability]:
    resources_spec = requirements.resources
    assert isinstance(resources_spec.cpu, CPUSpec)
    cpu_request = resources_spec.cpu.count.min or 0
    memory_mib_request = round((resources_spec.memory.min or 0) * 1024)
    gpu_request = 0
    if (gpu_spec := resources_spec.gpu) is not None:
        gpu_request = get_gpu_request_from_gpu_spec(gpu_spec)
    disk_mib_request = 0
    if (disk_spec := resources_spec.disk) is not None:
        disk_mib_request = round((disk_spec.size.min or 0) * 1024)

    nodes_allocated_resources = _get_nodes_allocated_resources(api)
    offers: list[InstanceOfferWithAvailability] = []
    for node in api.list_node().items:
        if (node_name := get_node_name(node)) is None:
            continue
        offer = _get_instance_offer_from_node(
            node=node,
            node_name=node_name,
            node_allocated_resources=nodes_allocated_resources.get(node_name),
            cpu_request=cpu_request,
            memory_mib_request=memory_mib_request,
            gpu_request=gpu_request,
            disk_mib_request=disk_mib_request,
        )
        if offer is not None:
            offers.extend(filter_offers_by_requirements([offer], requirements))
    return offers


def get_instance_offer_from_node(
    node: V1Node,
    *,
    cpu_request: int,
    memory_mib_request: int,
    gpu_request: int,
    disk_mib_request: int,
) -> Optional[InstanceOfferWithAvailability]:
    node_name = get_node_name(node)
    if node_name is None:
        return None
    return _get_instance_offer_from_node(
        node=node,
        node_name=node_name,
        node_allocated_resources=None,
        cpu_request=cpu_request,
        memory_mib_request=memory_mib_request,
        gpu_request=gpu_request,
        disk_mib_request=disk_mib_request,
    )


def get_nvidia_gpu_from_node_labels(labels: dict[str, str]) -> Optional[Gpu]:
    # We rely on https://github.com/NVIDIA/k8s-device-plugin/tree/main/docs/gpu-feature-discovery
    # to detect gpus. Note that "nvidia.com/gpu.product" is not a short gpu name like "T4" or
    # "A100" but a product name like "Tesla-T4" or "A100-SXM4-40GB".
    # Thus, we convert the product name to a known gpu name.
    gpu_product = labels.get(NVIDIA_GPU_PRODUCT_LABEL)
    if gpu_product is None:
        return None
    gpu_product = gpu_product.replace("RTX-", "RTX")
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


def get_amd_gpu_from_node_labels(labels: dict[str, str]) -> Optional[Gpu]:
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


def _get_instance_offer_from_node(
    node: V1Node,
    node_name: str,
    node_allocated_resources: Optional[KubernetesResources],
    cpu_request: int,
    memory_mib_request: int,
    gpu_request: int,
    disk_mib_request: int,
) -> Optional[InstanceOfferWithAvailability]:
    try:
        node_spec = get_or_error(node.spec)
        if any(is_hard_taint(t) and not is_taint_tolerated(t) for t in node_spec.taints or []):
            logger.debug("Node %s: untolerated taint(s) found, skipping", node_name)
            return None
        node_status = get_or_error(node.status)
        allocatable = get_or_error(node_status.allocatable)
        _cpu_arch: Optional[str] = None
        if node_status.node_info is not None:
            _cpu_arch = node_status.node_info.architecture
        cpu_arch = normalize_arch(_cpu_arch).to_cpu_architecture()
    except ValueError as e:
        logger.exception("Failed to process node %s: %s: %s", node_name, type(e).__name__, e)
        return None

    node_resources = KubernetesResources.from_kubernetes_map(allocatable)
    if node_allocated_resources is not None:
        node_resources = node_resources - node_allocated_resources
    cpu = max(0, int(node_resources.cpu))
    memory_mib = max(0, int(node_resources.memory / 2**20))
    disk_mib = max(0, int(node_resources.ephemeral_storage / 2**20))
    gpus = _get_gpus_from_node(node, node_name, node_resources)

    return InstanceOfferWithAvailability(
        backend=BackendType.KUBERNETES,
        instance=InstanceType(
            name=node_name,
            resources=Resources(
                cpus=min(cpu_request, cpu),
                cpu_arch=cpu_arch,
                memory_mib=min(memory_mib_request, memory_mib),
                gpus=gpus[:gpu_request],
                disk=Disk(size_mib=min(disk_mib_request, disk_mib)),
                spot=False,
            ),
        ),
        price=0,
        region=DUMMY_REGION,
        availability=InstanceAvailability.AVAILABLE,
        instance_runtime=InstanceRuntime.RUNNER,
    )


def _get_gpus_from_node(
    node: V1Node, node_name: str, node_resources: KubernetesResources
) -> list[Gpu]:
    labels = get_node_labels(node)
    for gpu_resource, gpu_getter in (
        (NVIDIA_GPU_RESOURCE, get_nvidia_gpu_from_node_labels),
        (AMD_GPU_RESOURCE, get_amd_gpu_from_node_labels),
    ):
        gpu_count = int(node_resources[gpu_resource])
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
    logger.debug("Node %s: no available GPU resource found", node_name)
    return []


def _get_nodes_allocated_resources(api: CoreV1Api) -> dict[str, KubernetesResources]:
    nodes_allocated_resources: dict[str, KubernetesResources] = {}
    for pod in api.list_pod_for_all_namespaces().items:
        pod_status = get_or_error(pod.status)
        pod_phase = PodPhase(get_or_error(pod_status.phase))
        if pod_phase.is_finished():
            continue
        pod_spec = get_or_error(pod.spec)
        node_name = pod_spec.node_name
        if node_name is None:
            continue
        pod_requests = KubernetesResources()
        # TODO: Should we also check PodSpec.resources? As of 2026-01-21, it's in alpha
        for container in pod_spec.containers:
            if container.resources is not None and container.resources.requests:
                pod_requests += KubernetesResources.from_kubernetes_map(
                    container.resources.requests
                )
        try:
            nodes_allocated_resources[node_name] += pod_requests
        except KeyError:
            nodes_allocated_resources[node_name] = pod_requests
    return nodes_allocated_resources
