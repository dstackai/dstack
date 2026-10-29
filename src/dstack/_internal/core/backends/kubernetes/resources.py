import base64
import dataclasses
import functools
import json
import operator
import re
from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Literal, Optional, Union, cast, get_args

import gpuhunt
from gpuhunt import KNOWN_AMD_GPUS, KNOWN_NVIDIA_GPUS, AcceleratorVendor
from kubernetes.client import CoreV1Api, V1Node, V1Taint
from kubernetes.utils.quantity import parse_quantity as _parse_quantity
from typing_extensions import Self

from dstack._internal.core.backends.base.compute import normalize_arch
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel, validate_extra_ignore
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import Memory, ResourcesSpec
from dstack._internal.utils import docker as docker_utils
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names
OBJECT_NAME_MAX_LENGTH = 253

# https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#syntax-and-character-set
LABEL_KEY_PREFIX_MAX_LENGTH = 253
LABEL_KEY_PREFIX_REGEX = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$"
)
LABEL_KEY_NAME_MAX_LENGTH = 63
LABEL_KEY_NAME_REGEX = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$")
LABEL_VALUE_MAX_LENGTH = 63
LABEL_VALUE_REGEX = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)?$")

NVIDIA_GPU_RESOURCE = "nvidia.com/gpu"
NVIDIA_GPU_NODE_TAINT = NVIDIA_GPU_RESOURCE
NVIDIA_GPU_PRODUCT_LABEL = f"{NVIDIA_GPU_RESOURCE}.product"
# With the `mixed` MIG strategy, the NVIDIA device plugin advertises MIG slices as a separate
# resource per MIG profile, e.g., nvidia.com/mig-1g.10gb (`+` in profile names is replaced
# with `.`, e.g., nvidia.com/mig-1g.10gb.me for 1g.10gb+me). GPUs with MIG disabled stay
# nvidia.com/gpu. See https://docs.nvidia.com/datacenter/cloud-native/kubernetes/latest/index.html
NVIDIA_MIG_RESOURCE_PREFIX = "nvidia.com/mig-"
# With the `single` MIG strategy, MIG slices are advertised as nvidia.com/gpu, and GPU Feature
# Discovery appends the MIG profile to the product label, e.g., A100-SXM4-80GB-MIG-1g.10gb.
# An invalid MIG layout is labeled as A100-SXM4-80GB-MIG-INVALID.
NVIDIA_MIG_PRODUCT_SEPARATOR = "-MIG-"
# The <compute slices>g.<memory>gb part of a MIG profile name, e.g., 1g.10gb. Suffixes such as
# +me, +me.all, -me, or +gfx don't change the memory.
# See https://docs.nvidia.com/datacenter/tesla/mig-user-guide/latest/supported-mig-profiles.html
MIG_PROFILE_MEMORY_REGEX = re.compile(r"^\d+g\.(\d+)gb")

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

    @classmethod
    def from_gpu_vendor(cls, vendor: gpuhunt.AcceleratorVendor) -> "AnyKubernetesGPUResource":
        match vendor:
            case gpuhunt.AcceleratorVendor.NVIDIA:
                return KubernetesResource.NVIDIA_GPU
            case gpuhunt.AcceleratorVendor.AMD:
                return KubernetesResource.AMD_GPU
        raise ValueError(f"Unsupported accelerator vendor: {vendor}")


AnyKubernetesGPUResource = Literal[KubernetesResource.NVIDIA_GPU, KubernetesResource.AMD_GPU]
GPU_RESOURCES: tuple[AnyKubernetesGPUResource, ...] = get_args(AnyKubernetesGPUResource)


@dataclasses.dataclass
class KubernetesResources:
    cpu: Decimal = Decimal("0")
    memory: Decimal = Decimal("0")
    ephemeral_storage: Decimal = Decimal("0")
    nvidia_gpu: Decimal = Decimal("0")
    amd_gpu: Decimal = Decimal("0")
    nvidia_mig: dict[str, Decimal] = dataclasses.field(default_factory=dict)
    """`mixed` strategy MIG slices by resource name, e.g., `nvidia.com/mig-1g.10gb`."""

    @classmethod
    def from_kubernetes_map(cls, map_: Mapping[str, str]) -> Self:
        dct: dict[str, Decimal] = {}
        for resource in KubernetesResource:
            if (qty := map_.get(resource.value)) is not None:
                dct[resource.name.lower()] = parse_quantity(qty)
        nvidia_mig = {
            resource: parse_quantity(qty)
            for resource, qty in map_.items()
            if resource.startswith(NVIDIA_MIG_RESOURCE_PREFIX)
        }
        return cls(**dct, nvidia_mig=nvidia_mig)

    def __getitem__(self, key: str) -> Decimal:
        if key.startswith(NVIDIA_MIG_RESOURCE_PREFIX):
            return self.nvidia_mig.get(key, Decimal("0"))
        try:
            resource = KubernetesResource(key)
        except ValueError:
            raise KeyError(key)
        return getattr(self, resource.name.lower())

    def __add__(self, other: Self) -> Self:
        return self._combine(other, operator.add)

    def __sub__(self, other: Self) -> Self:
        return self._combine(other, operator.sub)

    def _combine(self, other: Self, op: Callable[[Decimal, Decimal], Decimal]) -> Self:
        dct: dict[str, Decimal] = {}
        for resource in KubernetesResource:
            field = resource.name.lower()
            dct[field] = op(getattr(self, field), getattr(other, field))
        nvidia_mig = {
            resource: op(self[resource], other[resource])
            for resource in self.nvidia_mig.keys() | other.nvidia_mig.keys()
        }
        return type(self)(**dct, nvidia_mig=nvidia_mig)


@dataclasses.dataclass(frozen=True)
class ResourceRequestsLimits:
    cpu: Optional[int]
    memory_mib: Optional[int]
    disk_mib: Optional[int]
    gpu: int

    def to_kubernetes_map(
        self, gpu_resource: Optional[Union[AnyKubernetesGPUResource, str]] = None
    ) -> dict[str, str]:
        """
        Args:
            gpu_resource: `nvidia.com/gpu`, `amd.com/gpu`, or a `mixed` strategy MIG resource,
                e.g., `nvidia.com/mig-1g.10gb`. Required if GPUs are requested.
        """
        dct: dict[str, str] = {}
        if self.cpu is not None:
            dct[KubernetesResource.CPU.value] = str(self.cpu)
        if self.memory_mib is not None:
            dct[KubernetesResource.MEMORY.value] = f"{self.memory_mib}Mi"
        if self.disk_mib is not None:
            dct[KubernetesResource.EPHEMERAL_STORAGE.value] = f"{self.disk_mib}Mi"
        if self.gpu > 0:
            if gpu_resource is None:
                raise ValueError("gpu_resource is not specified")
            if isinstance(gpu_resource, KubernetesResource):
                gpu_resource = gpu_resource.value
            dct[gpu_resource] = str(self.gpu)
        return dct


@dataclasses.dataclass(frozen=True)
class ResourceRequests(ResourceRequestsLimits):
    cpu: int
    memory_mib: int
    disk_mib: int

    @classmethod
    def from_resources_spec(cls, spec: ResourcesSpec) -> Self:
        cpu = spec.cpu.count.min or 0
        memory_mib: int = 0
        if spec.memory.min is not None:
            memory_mib = round(spec.memory.min * 1024)
        disk_mib: int = 0
        if spec.disk is not None and spec.disk.size.min is not None:
            disk_mib = round(spec.disk.size.min * 1024)
        gpu: int = 0
        if spec.gpu is not None:
            gpu = spec.gpu.count.min or 0
        return cls(
            cpu=cpu,
            memory_mib=memory_mib,
            disk_mib=disk_mib,
            gpu=gpu,
        )

    @classmethod
    def from_kubernetes_map(cls, map_: Mapping[str, str]) -> Self:
        cpu_qty = map_.get(KubernetesResource.CPU.value, "0")
        cpu = round(parse_quantity(cpu_qty))
        memory_qty = map_.get(KubernetesResource.MEMORY.value, "0")
        memory_mib = round(parse_quantity(memory_qty) / 2**20)
        disk_qty = map_.get(KubernetesResource.EPHEMERAL_STORAGE.value, "0")
        disk_mib = round(parse_quantity(disk_qty) / 2**20)
        gpu: int = 0
        gpu_resource = get_gpu_resource_from_kubernetes_map(map_)
        if gpu_resource is not None:
            gpu = round(parse_quantity(map_[gpu_resource]))
        return cls(
            cpu=cpu,
            memory_mib=memory_mib,
            disk_mib=disk_mib,
            gpu=gpu,
        )


@dataclasses.dataclass(frozen=True)
class ResourceLimits(ResourceRequestsLimits):
    @classmethod
    def from_resources_spec(cls, spec: ResourcesSpec) -> Self:
        cpu = spec.cpu.count.max
        memory_mib: Optional[int] = None
        if spec.memory.max is not None:
            memory_mib = round(spec.memory.max * 1024)
        disk_mib: Optional[int] = None
        if spec.disk is not None:
            if spec.disk.size.max is not None:
                disk_mib = round(spec.disk.size.max * 1024)
        gpu: int = 0
        if spec.gpu is not None:
            # GPU resources cannot be overcommitted, limit must be equal to request
            gpu = spec.gpu.count.min or 0
        return cls(
            cpu=cpu,
            memory_mib=memory_mib,
            disk_mib=disk_mib,
            gpu=gpu,
        )


def get_gpu_resource_from_kubernetes_map(map_: Mapping[str, str]) -> Optional[str]:
    """
    Returns the GPU resource in a container's resource requests or limits map: `nvidia.com/gpu`,
    `amd.com/gpu`, or a `mixed` strategy MIG resource, e.g., `nvidia.com/mig-1g.10gb`.
    """
    for gpu_resource in GPU_RESOURCES:
        if gpu_resource.value in map_:
            return gpu_resource.value
    for resource in map_:
        if resource.startswith(NVIDIA_MIG_RESOURCE_PREFIX):
            return resource
    return None


def adjust_resources_by_resource_requests(
    resources: Resources,
    resource_requests: ResourceRequests,
    *,
    force: bool = False,
) -> None:
    cpu = resource_requests.cpu
    if not force:
        cpu = min(resources.cpus, cpu)
    resources.cpus = cpu
    memory_mib = resource_requests.memory_mib
    if not force:
        memory_mib = min(resources.memory_mib, memory_mib)
    resources.memory_mib = memory_mib
    resources.gpus = resources.gpus[: resource_requests.gpu]
    disk_mib = resource_requests.disk_mib
    if not force:
        disk_mib = min(resources.disk.size_mib, disk_mib)
    resources.disk = Disk(size_mib=disk_mib)


def build_base_labels(
    *,
    component: Literal["ssh-proxy", "job", "gateway", "volume"],
    unique_name: str,
    project: str,
    name: Optional[str] = None,
    user: Optional[str] = None,
) -> dict[str, str]:
    labels = {
        "app.kubernetes.io/name": f"dstack-{component}",
        # app.kubernetes.io/component would be redundant as app.kubernetes.io/name already includes
        # it with dstack- prefix
        "app.kubernetes.io/instance": unique_name,
        "app.kubernetes.io/managed-by": "dstack",
        "k8s.dstack.ai/project": project,
    }
    if name is not None:
        labels["k8s.dstack.ai/name"] = name
    if user is not None:
        labels["k8s.dstack.ai/user"] = user
    return labels


def filter_invalid_labels(labels: dict[str, str]) -> dict[str, str]:
    filtered_labels: dict[str, str] = {}
    for k, v in labels.items():
        try:
            validate_label_key(k)
            validate_label_value(v)
        except ValueError as e:
            logger.warning("Skipping invalid label %s=%s: %s", k, v, e)
            continue
        filtered_labels[k] = v
    return filtered_labels


def validate_label_key(key: str) -> None:
    parts = key.split("/")
    if len(parts) > 2:
        raise ValueError("Too many segments")
    name: str
    if len(parts) == 2:
        prefix, name = parts
        if not prefix:
            raise ValueError("Empty prefix")
        if len(prefix) > LABEL_KEY_PREFIX_MAX_LENGTH:
            raise ValueError("Prefix too long")
        if LABEL_KEY_PREFIX_REGEX.fullmatch(prefix) is None:
            raise ValueError("Invalid prefix")
    else:
        name = parts[0]
    if not name:
        raise ValueError("Empty name")
    if len(name) > LABEL_KEY_NAME_MAX_LENGTH:
        raise ValueError("Name too long")
    if LABEL_KEY_NAME_REGEX.fullmatch(name) is None:
        raise ValueError("Invalid name")


def validate_label_value(value: str) -> None:
    if len(value) > LABEL_VALUE_MAX_LENGTH:
        raise ValueError("Value too long")
    if LABEL_VALUE_REGEX.fullmatch(value) is None:
        raise ValueError("Invalid value")


def build_dockerconfigjson(image_name: str, username: str, password: str) -> str:
    registry = docker_utils.parse_image_name(image_name).registry
    if registry is None or docker_utils.is_default_registry(registry):
        # https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/
        # > Use https://index.docker.io/v1/ for DockerHub
        registry = "https://index.docker.io/v1/"
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    entry = {
        "username": username,
        "password": password,
        "auth": auth,
    }
    return json.dumps({"auths": {registry: entry}})


parse_quantity = cast(Callable[[Union[str, int, float, Decimal]], Decimal], _parse_quantity)


def format_memory(memory: Memory) -> str:
    return f"{float(memory)}Gi"


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
    try:
        taint_effect = TaintEffect(taint.effect)
    except ValueError:
        logger.warning(
            "Unexpected taint %s=%s effect: %s", taint.key, taint.value or "", taint.effect
        )
        return True
    return taint_effect is not TaintEffect.PREFER_NO_SCHEDULE


def is_taint_tolerated(taint: V1Taint) -> bool:
    return taint.key in (NVIDIA_GPU_NODE_TAINT, AMD_GPU_NODE_TAINT)


class KubernetesOfferBackendData(CoreModel):
    mig: bool = False
    """Whether the offer's GPUs are NVIDIA MIG slices rather than whole GPUs."""
    mig_resource: Optional[str] = None
    """The `mixed` strategy MIG resource that pods request for the offer's GPUs, e.g.,
    `nvidia.com/mig-1g.10gb`. Not set for other offers, including `single` strategy MIG slices,
    whose pods request `nvidia.com/gpu` or `amd.com/gpu`."""

    @classmethod
    def load(cls, data: Mapping[str, Any]) -> Self:
        return validate_extra_ignore(cls, data)

    def dump(self) -> dict[str, Any]:
        # Offers without MIG slices keep empty backend data.
        return self.model_dump(exclude_defaults=True)


def get_instance_offers(
    api: CoreV1Api, region: str, unallocated_resources: bool
) -> list[InstanceOfferWithAvailability]:
    nodes_allocated_resources: Optional[dict[str, KubernetesResources]] = None
    if unallocated_resources:
        nodes_allocated_resources = _get_nodes_allocated_resources(api)
    offers: list[InstanceOfferWithAvailability] = []
    for node in api.list_node().items:
        if (node_name := get_node_name(node)) is None:
            continue
        offers.extend(
            _get_instance_offers_from_node(
                node=node,
                node_name=node_name,
                node_allocated_resources=(
                    None
                    if nodes_allocated_resources is None
                    else nodes_allocated_resources.get(node_name)
                ),
                region=region,
            )
        )
    return offers


def get_instance_offer_from_node(
    node: V1Node, region: str, gpu_resource: Optional[str] = None
) -> Optional[InstanceOfferWithAvailability]:
    """
    Returns the node's offer for `gpu_resource`: the offer for the `mixed` strategy MIG resource
    if `gpu_resource` is one, otherwise the node's main offer.
    """
    node_name = get_node_name(node)
    if node_name is None:
        return None
    mig_resource: Optional[str] = None
    if gpu_resource is not None and gpu_resource.startswith(NVIDIA_MIG_RESOURCE_PREFIX):
        mig_resource = gpu_resource
    offers = _get_instance_offers_from_node(
        node=node,
        node_name=node_name,
        node_allocated_resources=None,
        region=region,
    )
    for offer in offers:
        if KubernetesOfferBackendData.load(offer.backend_data).mig_resource == mig_resource:
            return offer
    return None


def get_nvidia_gpu_from_node_labels(
    labels: dict[str, str], mig_resource: Optional[str] = None
) -> Optional[Gpu]:
    """
    Returns the GPU that the node provides via `nvidia.com/gpu`, or via the `mixed` strategy MIG
    resource `mig_resource` if it is set.

    A MIG slice is returned with the parent GPU's name and the memory from the MIG profile name,
    e.g., A100 with 10GB for 1g.10gb, the same way whole GPUs have their nominal memory.
    """
    # We rely on https://github.com/NVIDIA/k8s-device-plugin/tree/main/docs/gpu-feature-discovery
    # to detect gpus. Note that "nvidia.com/gpu.product" is not a short gpu name like "T4" or
    # "A100" but a product name like "Tesla-T4" or "A100-SXM4-40GB".
    # Thus, we convert the product name to a known gpu name.
    gpu_product = labels.get(NVIDIA_GPU_PRODUCT_LABEL)
    if gpu_product is None:
        return None
    # With the `single` MIG strategy, the product label ends with -MIG-<profile>. With the
    # `mixed` strategy, it is the parent GPU's product name.
    gpu_product, _, mig_profile = gpu_product.partition(NVIDIA_MIG_PRODUCT_SEPARATOR)
    if mig_resource is not None:
        mig_profile = mig_resource.removeprefix(NVIDIA_MIG_RESOURCE_PREFIX)
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
    if mig_profile:
        mig_memory = _get_mig_memory_mib(mig_profile)
        if mig_memory is None:
            logger.warning("Failed to detect memory of MIG profile %s", mig_profile)
            return None
        gpu_memory = mig_memory
    return Gpu(vendor=AcceleratorVendor.NVIDIA, name=gpu_name, memory_mib=gpu_memory)


def is_nvidia_mig_product(labels: dict[str, str]) -> bool:
    """
    Returns whether the node's `nvidia.com/gpu` resource provides `single` strategy MIG slices.
    """
    return NVIDIA_MIG_PRODUCT_SEPARATOR in labels.get(NVIDIA_GPU_PRODUCT_LABEL, "")


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


def _get_instance_offers_from_node(
    node: V1Node,
    node_name: str,
    node_allocated_resources: Optional[KubernetesResources],
    region: str,
) -> list[InstanceOfferWithAvailability]:
    """
    Returns the node's main offer, with the node's `nvidia.com/gpu` or `amd.com/gpu` GPUs, if any,
    followed by an offer for each `mixed` strategy MIG resource with available slices.
    """
    try:
        node_spec = get_or_error(node.spec)
        if any(is_hard_taint(t) and not is_taint_tolerated(t) for t in node_spec.taints or []):
            logger.debug("Node %s: untolerated taint(s) found, skipping", node_name)
            return []
        node_status = get_or_error(node.status)
        allocatable = get_or_error(node_status.allocatable)
        _cpu_arch: Optional[str] = None
        if node_status.node_info is not None:
            _cpu_arch = node_status.node_info.architecture
        cpu_arch = normalize_arch(_cpu_arch).to_cpu_architecture()
    except ValueError as e:
        logger.exception("Failed to process node %s: %s: %s", node_name, type(e).__name__, e)
        return []

    node_resources = KubernetesResources.from_kubernetes_map(allocatable)
    if node_allocated_resources is not None:
        node_resources = node_resources - node_allocated_resources
    cpu = max(0, int(node_resources.cpu))
    memory_mib = max(0, int(node_resources.memory / 2**20))
    disk_mib = max(0, int(node_resources.ephemeral_storage / 2**20))
    labels = get_node_labels(node)
    gpus = _get_gpus_from_node(node, node_name, node_resources)
    make_offer = functools.partial(
        _make_instance_offer,
        node_name=node_name,
        region=region,
        cpu=cpu,
        cpu_arch=cpu_arch,
        memory_mib=memory_mib,
        disk_mib=disk_mib,
    )
    offers = [
        make_offer(
            gpus=gpus,
            backend_data=KubernetesOfferBackendData(
                mig=(
                    len(gpus) > 0
                    and gpus[0].vendor == AcceleratorVendor.NVIDIA
                    and is_nvidia_mig_product(labels)
                ),
            ),
        )
    ]
    # With the `mixed` MIG strategy, each MIG profile is a separate resource, and a pod can
    # request only one of them, so each gets its own offer. The offers share the node's CPU,
    # memory, and disk.
    for mig_resource, mig_gpus in _get_nvidia_mig_gpus_from_node(
        labels, node_name, node_resources
    ):
        offers.append(
            make_offer(
                gpus=mig_gpus,
                backend_data=KubernetesOfferBackendData(mig=True, mig_resource=mig_resource),
            )
        )
    return offers


def _make_instance_offer(
    *,
    node_name: str,
    region: str,
    cpu: int,
    cpu_arch: gpuhunt.CPUArchitecture,
    memory_mib: int,
    disk_mib: int,
    gpus: list[Gpu],
    backend_data: KubernetesOfferBackendData,
) -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.KUBERNETES,
        instance=InstanceType(
            name=node_name,
            resources=Resources(
                cpus=cpu,
                cpu_arch=cpu_arch,
                memory_mib=memory_mib,
                gpus=gpus,
                disk=Disk(size_mib=disk_mib),
                spot=False,
            ),
        ),
        price=0,
        region=region,
        availability=InstanceAvailability.AVAILABLE,
        instance_runtime=InstanceRuntime.RUNNER,
        backend_data=backend_data.dump(),
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


def _get_nvidia_mig_gpus_from_node(
    labels: dict[str, str], node_name: str, node_resources: KubernetesResources
) -> list[tuple[str, list[Gpu]]]:
    """
    Returns `(mig_resource, gpus)` pairs for the node's `mixed` strategy MIG resources with
    available slices.
    """
    mig_gpus: list[tuple[str, list[Gpu]]] = []
    for mig_resource, mig_qty in sorted(node_resources.nvidia_mig.items()):
        mig_count = int(mig_qty)
        if mig_count < 1:
            continue
        gpu = get_nvidia_gpu_from_node_labels(labels, mig_resource)
        if gpu is None:
            logger.warning(
                "Node %s: MIG resource found, but failed to detect its GPU: %s=%d",
                node_name,
                mig_resource,
                mig_count,
            )
            continue
        mig_gpus.append((mig_resource, [gpu] * mig_count))
    return mig_gpus


def _get_mig_memory_mib(mig_profile: str) -> Optional[int]:
    match = MIG_PROFILE_MEMORY_REGEX.match(mig_profile)
    if match is None:
        return None
    return int(match.group(1)) * 1024


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
