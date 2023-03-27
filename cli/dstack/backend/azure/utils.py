def get_storage_account_id(subscription_id: str, resource_group: str, storage_account: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{storage_account}"


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
