from typing import Dict, Iterator, List, Optional

from dstack._internal.core.configuration import PortMapping
from dstack._internal.core.error import DstackError

RESERVED_PORTS_START = 10000
RESERVED_PORTS_END = 10999


class PortUsedError(DstackError):
    pass


def merge_ports(schema: List[PortMapping], args: List[PortMapping]) -> Dict[int, PortMapping]:
    unique_ports_constraint([pm.container_port for pm in schema])
    unique_ports_constraint([pm.container_port for pm in args])

    ports = {pm.container_port: pm for pm in schema}
    for pm in args:  # override schema
        ports[pm.container_port] = pm

    unique_ports_constraint([pm.local_port for pm in ports.values() if pm.local_port is not None])
    return ports


def unique_ports_constraint(
    ports: List[int],
    error: str = "Port {} is already in use",
):
    used_ports = set()
    for i in ports:
        if i in used_ports:
            raise PortUsedError(error.format(i))
        used_ports.add(i)


def get_map_to_port(ports: Dict[int, PortMapping], port: int) -> Optional[int]:
    if port in ports:
        return ports[port].local_port
    return None


def filter_reserved_ports(ports: Dict[int, PortMapping]) -> Iterator[PortMapping]:
    for i in ports.values():
        if RESERVED_PORTS_START <= i.container_port <= RESERVED_PORTS_END:
            continue
        yield i
