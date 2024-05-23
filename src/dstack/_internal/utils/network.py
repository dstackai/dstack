import ipaddress
from typing import Optional, Sequence


def get_ip_from_network(network: Optional[str], addresses: Sequence[str]) -> Optional[str]:
    ip_addresses = []
    for address in addresses:
        try:
            interface = ipaddress.IPv4Interface(address)
            ip_addresses.append(interface.ip)
        except ipaddress.AddressValueError:
            continue

    internal_network = None
    if network is not None:
        if not ip_addresses:
            return None
        try:
            internal_network = ipaddress.ip_network(network)
        except ValueError:
            return None

        if not internal_network.is_private:
            return None

        for internal_ip in ip_addresses:
            if internal_ip in internal_network:
                return str(internal_ip)
        else:
            return None

    # return any ipv4
    internal_ip = str(ip_addresses[0]) if ip_addresses else None
    return internal_ip
