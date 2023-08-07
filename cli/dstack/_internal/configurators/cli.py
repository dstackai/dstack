import re
from typing import Dict, Tuple

import dstack._internal.configurators.ports as ports


def port_mapping(v: str) -> ports.PortMapping:
    # argparse uses __name__ for handling ValueError
    return ports.PortMapping.parse(v)


def env_var(v: str) -> Tuple[str, str]:
    r = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)=(.*)$", v)
    if r is None:
        raise ValueError(v)
    key, value = r.groups()
    return key, value


def gpu_resource(v: str) -> Dict[str, str]:
    patterns = {
        "name": r"^[a-z].+$",  # GPU name starts with a letter
        "count": r"^\d+$",  # Count contains digits only
        "memory": r"^\d+(mb|gb)$",  # Memory has a suffix
    }
    data = {}
    for part in v.split(":"):
        for key, pattern in patterns.items():
            if re.match(pattern, part.lower()) is not None:
                data[key] = part
                patterns.pop(key)  # every field could be used at most once
                break
        else:
            raise ValueError(part)
    return data
