DSTACK_CONTAINER_NAME = "dstack-container"
DSTACK_LOGS_TABLE_NAME = "dstack_logs_CL"
DSTACK_NETWORK_SECURITY_GROUP = "dstack-network-security-group"


def get_resource_group_id(subscription_id: str, resource_group: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"


def get_key_vault_id(subscription_id: str, resource_group: str, key_vault) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.KeyVault/vaults/{key_vault}"


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


def get_data_collection_rule_id(subscription_id: str, resource_group: str, dcr_name: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Insights/dataCollectionRules/{dcr_name}"


def get_data_collection_endpoint_id(
    subscription_id: str, resource_group: str, dce_name: str
) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Insights/dataCollectionEndpoints/{dce_name}"


def get_resource_group_from_resource_id(resource_id: str) -> str:
    return resource_id.split("/")[4]


def get_blob_storage_account_url(storage_account: str) -> str:
    return f"https://{storage_account}.blob.core.windows.net"


def get_runner_managed_identity_name(storage_account: str) -> str:
    return f"{storage_account}-runner-identity"


def get_key_vault_name(storage_account: str) -> str:
    return storage_account


def get_default_network_name(storage_account: str) -> str:
    return f"{storage_account}-default-network"


def get_default_subnet_name(storage_account: str) -> str:
    return f"{storage_account}-default-subnet"


def get_logs_workspace_name(storage_account: str) -> str:
    return f"{storage_account}-workspace"


def get_data_collection_endpoint_name(storage_account: str) -> str:
    return f"{storage_account}-dce"


def get_data_collection_rule_name(storage_account: str) -> str:
    return f"{storage_account}-dcr"
