from typing import Dict, Optional

from dstack.backend.base.config import BackendConfig


class AzureConfig(BackendConfig):
    NAME = "azure"

    def __init__(
        self,
        tenant_id: str,
        subscription_id: str,
        location: str,
        resource_group: str,
        storage_account: str,
        vault_url: str,
        network: str,
        subnet: str,
        credentials: Dict,
    ):
        self.subscription_id = subscription_id
        self.tenant_id = tenant_id
        self.location = location
        self.resource_group = resource_group
        self.storage_account = storage_account
        self.vault_url = vault_url
        self.network = network
        self.subnet = subnet
        self.credentials = credentials

    def serialize(self) -> Dict:
        res = {
            "backend": "azure",
            "tenant_id": self.tenant_id,
            "subscription_id": self.subscription_id,
            "location": self.location,
            "resource_group": self.resource_group,
            "storage_account": self.storage_account,
            "vault_url": self.vault_url,
            "network": self.network,
            "subnet": self.subnet,
        }
        return res

    @classmethod
    def deserialize(cls, data: Dict) -> Optional["AzureConfig"]:
        if data.get("backend") != "azure":
            return None

        try:
            tenant_id = data["tenant_id"]
            subscription_id = data["subscription_id"]
            location = data["location"]
            resource_group = data["resource_group"]
            storage_account = data["storage_account"]
            vault_url = data["vault_url"]
            network = data["network"]
            subnet = data["subnet"]
            credentials = {
                "client_id": data["client_id"],
                "client_secret": data["client_secret"],
            }
        except KeyError:
            return None

        return cls(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            location=location,
            resource_group=resource_group,
            storage_account=storage_account,
            vault_url=vault_url,
            network=network,
            subnet=subnet,
            credentials=credentials,
        )
