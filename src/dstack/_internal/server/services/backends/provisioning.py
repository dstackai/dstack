import re

from dstack._internal import settings
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.runs import JobProvisioningData, JobSpec
from dstack._internal.core.models.volumes import InstanceMountPoint
from dstack._internal.server.schemas.runner import GPUDevice

_AWS_EFA_ENABLED_INSTANCE_TYPE_PATTERNS = [
    # TODO: p6-b200 isn't supported yet in gpuhunt
    r"^p6-b200\.(48xlarge)$",
    r"^p5\.(4xlarge|48xlarge)$",
    r"^p5e\.(48xlarge)$",
    r"^p5en\.(48xlarge)$",
    r"^p4d\.(24xlarge)$",
    r"^p4de\.(24xlarge)$",
    r"^g6\.(8xlarge|12xlarge|16xlarge|24xlarge|48xlarge)$",
    r"^g6e\.(8xlarge|12xlarge|16xlarge|24xlarge|48xlarge)$",
    r"^gr6\.8xlarge$",
    r"^g5\.(8xlarge|12xlarge|16xlarge|24xlarge|48xlarge)$",
    r"^g4dn\.(8xlarge|12xlarge|16xlarge|metal)$",
    r"^p3dn\.(24xlarge)$",
]


def get_instance_specific_mounts(
    backend_type: BackendType,
    instance_type_name: str,
) -> list[InstanceMountPoint]:
    if backend_type == BackendType.GCP:
        if instance_type_name == "a3-megagpu-8g":
            return [
                InstanceMountPoint(
                    instance_path="/dev/aperture_devices",
                    path="/dev/aperture_devices",
                ),
                InstanceMountPoint(
                    instance_path="/var/lib/tcpxo/lib64",
                    path="/var/lib/tcpxo/lib64",
                ),
                InstanceMountPoint(
                    instance_path="/var/lib/fastrak/lib64",
                    path="/var/lib/fastrak/lib64",
                ),
            ]
        if instance_type_name in ["a3-edgegpu-8g", "a3-highgpu-8g"]:
            return [
                InstanceMountPoint(
                    instance_path="/var/lib/nvidia/lib64",
                    path="/usr/local/nvidia/lib64",
                ),
                InstanceMountPoint(
                    instance_path="/var/lib/nvidia/bin",
                    path="/usr/local/nvidia/bin",
                ),
                InstanceMountPoint(
                    instance_path="/var/lib/tcpx/lib64",
                    path="/usr/local/tcpx/lib64",
                ),
                InstanceMountPoint(
                    instance_path="/run/tcpx",
                    path="/run/tcpx",
                ),
            ]
    return []


def get_instance_specific_gpu_devices(
    backend_type: BackendType,
    instance_type_name: str,
) -> list[GPUDevice]:
    gpu_devices = []
    if backend_type == BackendType.GCP and instance_type_name in [
        "a3-edgegpu-8g",
        "a3-highgpu-8g",
    ]:
        for i in range(8):
            gpu_devices.append(
                GPUDevice(path_on_host=f"/dev/nvidia{i}", path_in_container=f"/dev/nvidia{i}")
            )
        gpu_devices.append(
            GPUDevice(path_on_host="/dev/nvidia-uvm", path_in_container="/dev/nvidia-uvm")
        )
        gpu_devices.append(
            GPUDevice(path_on_host="/dev/nvidiactl", path_in_container="/dev/nvidiactl")
        )
    return gpu_devices


def resolve_provisioning_image_name(
    job_spec: JobSpec,
    job_provisioning_data: JobProvisioningData,
) -> str:
    image_name = job_spec.image_name
    if job_provisioning_data.backend == BackendType.AWS:
        return _patch_base_image_for_aws_efa(
            image_name,
            job_provisioning_data.instance_type.name,
        )
    return image_name


def _patch_base_image_for_aws_efa(
    image_name: str,
    instance_type_name: str,
) -> str:
    is_efa_enabled = any(
        re.match(pattern, instance_type_name)
        for pattern in _AWS_EFA_ENABLED_INSTANCE_TYPE_PATTERNS
    )
    if not is_efa_enabled:
        return image_name

    if not image_name.startswith(f"{settings.DSTACK_BASE_IMAGE}:"):
        return image_name

    if image_name.endswith(f"-base-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"):
        return image_name[:-17] + f"-devel-efa-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"
    if image_name.endswith(f"-devel-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"):
        return image_name[:-18] + f"-devel-efa-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"

    return image_name
