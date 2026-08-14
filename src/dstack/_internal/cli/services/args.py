from dstack._internal.core.models import resources as resources
from dstack._internal.core.models.configurations import PortMapping
from dstack._internal.core.models.envs import EnvVarTuple


def gpu_spec(v: str) -> resources.GPUSpec:
    return resources.GPUSpec.model_validate(v)


def env_var(v: str) -> EnvVarTuple:
    return EnvVarTuple.parse(v)


def port_mapping(v: str) -> PortMapping:
    return PortMapping.parse(v)


def cpu_spec(v: str) -> resources.CPUSpec:
    return resources.CPUSpec.model_validate(v)


def memory_spec(v: str) -> resources.Range[resources.Memory]:
    return resources.Range[resources.Memory].model_validate(v)


def disk_spec(v: str) -> resources.DiskSpec:
    return resources.DiskSpec.model_validate(v)
