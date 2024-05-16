import ipaddress
from typing import Optional, Sequence


def get_ip_from_network(network: Optional[str], addresses: Sequence[str]) -> Optional[str]:
    ip_addresses = []
    for address in addresses:
        try:
            ip, _, _ = address.partition("/")
            ip_addresses.append(ipaddress.IPv4Address(ip))
        except ipaddress.AddressValueError:
            continue

    internal_network = None
    if network is not None:
        try:
            internal_network = ipaddress.ip_network(network)
        except ValueError:
            pass

    if internal_network is not None:
        for internal_ip in ip_addresses:
            if internal_ip in internal_network:
                return str(internal_ip)
        else:
            return None

    # return any ipv4
    internal_ip = str(ip_addresses[0]) if ip_addresses else None
    return internal_ip
