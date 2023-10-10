def get_resource_name_from_resource_id(resource_id: str) -> str:
    return resource_id.split("/")[-1]


def get_resource_group_id(subscription_id: str, resource_group: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"


def get_runner_managed_identity_name(resource_group: str) -> str:
    return f"{resource_group}-runner-identity"


def get_default_network_name(resource_group: str, location: str) -> str:
    return f"{resource_group}-{location}-default-network"


def get_default_subnet_name(resource_group: str, location: str) -> str:
    return f"{resource_group}-{location}-default-subnet"


def get_default_network_security_group_name(resource_group: str, location: str) -> str:
    return f"{resource_group}-{location}-default-security-group"


def get_gateway_network_security_group_name(resource_group: str, location: str) -> str:
    return f"{resource_group}-{location}-gateway-security-group"


def get_managed_identity_id(
    subscription_id: str, resource_group: str, managed_identity: str
) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{managed_identity}"


def get_network_security_group_id(
    subscription_id: str, resource_group: str, network_security_group: str
) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Network/networkSecurityGroups/{network_security_group}"


def get_subnet_id(subscription_id: str, resource_group: str, network: str, subnet: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Network/virtualNetworks/{network}/subnets/{subnet}"
