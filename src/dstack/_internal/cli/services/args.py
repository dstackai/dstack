from typing import Dict

from pydantic import parse_obj_as

from dstack._internal.core.models import resources as resources
from dstack._internal.core.models.configurations import PortMapping
from dstack._internal.core.models.envs import EnvVarTuple


def gpu_spec(v: str) -> Dict:
    return resources.GPUSpec.parse(v)


def env_var(v: str) -> EnvVarTuple:
    return EnvVarTuple.parse(v)


def port_mapping(v: str) -> PortMapping:
    return PortMapping.parse(v)


def cpu_spec(v: str) -> dict:
    return resources.CPUSpec.parse(v)


def memory_spec(v: str) -> resources.Range[resources.Memory]:
    return parse_obj_as(resources.Range[resources.Memory], v)


def disk_spec(v: str) -> resources.DiskSpec:
    return parse_obj_as(resources.DiskSpec, v)
