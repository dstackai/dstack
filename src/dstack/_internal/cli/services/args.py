import re
from typing import Dict, Tuple

from pydantic import parse_obj_as

from dstack._internal.core.models import resources as resources
from dstack._internal.core.models.configurations import PortMapping


def gpu_spec(v: str) -> Dict:
    return resources.GPUSpec.parse(v)


def env_var(v: str) -> Tuple[str, str]:
    r = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)=(.*)$", v)
    if r is None:
        raise ValueError(v)
    key, value = r.groups()
    return key, value


def port_mapping(v: str) -> PortMapping:
    return PortMapping.parse(v)


def cpu_spec(v: str) -> resources.Range[int]:
    return parse_obj_as(resources.Range[int], v)


def memory_spec(v: str) -> resources.Range[resources.Memory]:
    return parse_obj_as(resources.Range[resources.Memory], v)


def disk_spec(v: str) -> resources.DiskSpec:
    return parse_obj_as(resources.DiskSpec, v)
