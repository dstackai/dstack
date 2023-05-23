import argparse
import re
from typing import Dict, Iterator, List, Optional, Union

from dstack.core.error import DstackError

RESERVED_PORTS_START = 10000
RESERVED_PORTS_END = 10999


class PortReservedError(DstackError):
    pass


class PortUsedError(DstackError):
    pass


class PortMapping:
    """
    Valid formats:
      - 1234
      - "1234"
      - "1234:5678"
    """

    def __init__(self, v: Union[str, int]):
        self.port: int
        self.map_to_port: Optional[int] = None

        if isinstance(v, int):
            self.port = v
            return
        r = re.search(r"^(\d+)(?::(\d+))?$", v)
        if r is None:
            raise argparse.ArgumentTypeError(f"{v} is not a valid port or port mapping")
        port, map_to_port = r.groups()
        self.port = int(port)
        if map_to_port is not None:
            self.map_to_port = int(map_to_port)

    def __repr__(self):
        s = str(self.port)
        if self.map_to_port is not None:
            s += f":{self.map_to_port}"
        return f'PortMapping("{s}")'


def merge_ports(schema: List[PortMapping], args: List[PortMapping]) -> Dict[int, PortMapping]:
    unique_ports_constraint([pm.port for pm in schema], error="Schema port {} is already in use")
    unique_ports_constraint([pm.port for pm in args], error="Args port {} is already in use")

    ports = {pm.port: pm for pm in schema}
    for pm in args:  # override schema
        ports[pm.port] = pm

    unique_ports_constraint(
        [pm.map_to_port for pm in ports.values() if pm.map_to_port is not None],
        error="Mapped port {} is already in use",
    )
    return ports


def unique_ports_constraint(ports: List[int], error: str = "Port {} is already in use"):
    used_ports = set()
    for i in ports:
        if i in used_ports:
            raise PortUsedError(error.format(i))
        used_ports.add(i)


def get_map_to_port(ports: Dict[int, PortMapping], port: int) -> Optional[int]:
    if port in ports:
        return ports[port].map_to_port
    return None


def filter_reserved_ports(ports: Dict[int, PortMapping]) -> Iterator[PortMapping]:
    for i in ports.values():
        if RESERVED_PORTS_START <= i.port <= RESERVED_PORTS_END:
            continue
        yield i
