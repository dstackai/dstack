import json
import re
from inspect import signature
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.keyvault.models import (
    AccessPolicyEntry,
    Permissions,
    SecretPermissions,
    Sku,
    Vault,
    VaultCreateOrUpdateParameters,
    VaultProperties,
)
from azure.mgmt.loganalytics import LogAnalyticsManagementClient
from azure.mgmt.loganalytics.models import Column, ColumnTypeEnum, Schema, Table, Workspace
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.monitor.models import (
    DataCollectionEndpointResource,
    DataCollectionRuleDestinations,
    DataCollectionRuleResource,
    DataFlow,
    LogAnalyticsDestination,
)
from azure.mgmt.msi import ManagedServiceIdentityClient
from azure.mgmt.msi.models import Identity
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import BlobContainer
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.subscription.models import Subscription, TenantIdDescription
from pydantic.error_wrappers import ValidationError
from pydantic.fields import Field
from pydantic.main import create_model
from pydantic.networks import stricturl
from pydantic.tools import parse_obj_as
from pydantic.types import constr
from rich.prompt import Prompt

from dstack.backend.azure import utils as azure_utils
from dstack.cli.common import ask_choice, console
from dstack.core.config import BackendConfig, Configurator, get_config_path
from dstack.core.error import ConfigError

# https://learn.microsoft.com/en-us/rest/api/resources/resource-groups/create-or-update?tabs=HTTP#uri-parameters
# The name of the resource group to create or update.
# Can include
# alphanumeric,
# underscore,
# parentheses,
# hyphen,
# period (except at end),
# and Unicode characters that match the allowed characters.
# ^[-\w\._\(\)]+$
group_name_validator = constr(
    regex=r"^[-\w\._\(\)]+[-\w_\(\)]$|^[-\w\._\(\)]$",
    min_length=1,
    max_length=90,
)

# XXX: Where is full inclusive description of requirements for url of Key Vault?
# This page says about "DNS Name":
# https://learn.microsoft.com/en-us/python/api/azure-keyvault-secrets/azure.keyvault.secrets.secretclient?view=azure-python#parameters
# This page says about "vaults" without any context:
# https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/resource-name-rules#microsoftkeyvault
# This page says about stop-words:
# https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-reserved-resource-name
# This page says vault name is part of url:
# https://learn.microsoft.com/en-us/azure/key-vault/general/about-keys-secrets-certificates#vault-name-and-object-name
# For Vaults: https://{vault-name}.vault.azure.net/{object-type}/{object-name}/{object-version}
# Vault name and Managed HSM pool name must be a 3-24 character string, containing only 0-9, a-z, A-Z, and -.
# Length:
# 3-24
# Valid Characters:
# - Alphanumerics and hyphens.
# - Start with letter. End with letter or digit. Can't contain consecutive hyphens.
vault_name_pattern = re.compile(r"^[a-z](?:-[0-9a-z]|[0-9a-z])$")
vault_name_min_length = 3
vault_name_max_length = 24

# https://learn.microsoft.com/en-us/azure/key-vault/general/about-keys-secrets-certificates#dns-suffixes-for-base-url
vault_dns_suffixes = frozenset(
    ("vault.azure.net", "vault.azure.cn", "vault.usgovcloudapi.net", "vault.microsoftazure.de")
)


# https://learn.microsoft.com/en-us/azure/storage/common/storage-account-overview#storage-account-name
# Storage account names must be between 3 and 24 characters in length and may contain numbers and lowercase letters only.
# It is ok for digit as first character.
storage_account_name_pattern = re.compile(r"^[a-z][0-9a-z]$")
storage_account_name_min_length = 3
storage_account_name_max_length = 24

# https://learn.microsoft.com/en-us/rest/api/storageservices/Naming-and-Referencing-Containers--Blobs--and-Metadata#resource-uri-syntax
# There are different storage types https://learn.microsoft.com/en-us/azure/storage/common/storage-account-overview#standard-endpoints
blob_dns_suffixes = frozenset(("blob.core.windows.net",))

# https://learn.microsoft.com/en-us/rest/api/storageservices/naming-and-referencing-containers--blobs--and-metadata#container-names
# - Container names must start or end with a letter or number, and can contain only letters, numbers, and the dash (-) character.
# - Every dash (-) character must be immediately preceded and followed by a letter or number; consecutive dashes are not permitted in container names.
# - All letters in a container name must be lowercase.
# - Container names must be from 3 through 63 characters long.
container_name_pattern = r"^[0-9a-z](?:-[0-9a-z]|[0-9a-z])$"
container_account_name_min_length = 3
container_account_name_max_length = 63
container_validator = constr(
    regex=container_name_pattern,
    min_length=container_account_name_min_length,
    max_length=container_account_name_max_length,
)


# XXX: It is based on approximate match with dstack.backend.aws.config.regions.
locations = [
    ("(US) East US, Virginia", "eastus"),
    ("(US) East US 2, Virginia", "eastus2"),
    ("(US) South Central US, Texas", "southcentralus"),
    ("(US) West US 2, Washington", "westus2"),
    ("(US) West US 3, Phoenix", "westus3"),
    ("(Asia Pacific) Southeast Asia, Singapore", "southeastasia"),
    ("(Canada) Canada Central, Toronto", "canadacentral"),
    ("(Europe) Germany West Central, Frankfurt", "germanywestcentral"),
    ("(Europe) North Europe, Ireland", "northeurope"),
    ("(Europe) UK South, London", "uksouth"),
    ("(Europe) France Central, Paris", "francecentral"),
    ("(Europe) Sweden Central, Gävle", "swedencentral"),
]


class AzureConfig(BackendConfig):
    NAME = "azure"

    def __init__(
        self,
        tenant_id: str,
        subscription_id: str,
        location: str,
        resource_group: str,
        storage_account: str,
        secret_url: str,
        network: str,
        subnet: str,
    ):
        self.subscription_id = subscription_id
        self.tenant_id = tenant_id
        self.location = location
        self.resource_group = resource_group
        self.secret_url = secret_url
        self.secret_vault = secret_url.host.split(".", 1)[0]
        self.storage_account = storage_account
        self.network = "dstackNetwork"
        self.subnet = "default"
        self.managed_identity = "dstackManagedIdentity"

    def serialize(self) -> Dict:
        res = {
            "backend": "azure",
            "tenant_id": self.tenant_id,
            "subscription_id": self.subscription_id,
            "location": self.location,
            "storage_account": self.storage_account,
            "network": self.network,
            "subnet": self.subnet,
        }
        return res

    def serialize_yaml(self) -> str:
        return yaml.dump(self.serialize())

    @classmethod
    def deserialize(cls, data: Dict) -> "AzureConfig":
        if data.get("backend") != "azure":
            raise ConfigError(f"Not an Azure config")

        try:
            tenant_id = data["tenant_id"]
            subscription_id = data["subscription_id"]
            location = data["location"]
            resource_group = data["resource_group"]
            storage_account = data["storage_account"]
            network = data["network"]
            subnet = data["subnet"]
        except KeyError:
            raise ConfigError("Cannot load config")

        return cls(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            location=location,
            resource_group=resource_group,
            storage_account=storage_account,
            network=network,
            subnet=subnet,
        )

    @classmethod
    def deserialize_yaml(cls, yaml_content: str) -> "AzureConfig":
        content = yaml.load(yaml_content, yaml.FullLoader)
        if content is None:
            raise ConfigError("Cannot load config")
        return cls.deserialize(content)

    @classmethod
    def load(cls, path: Path = get_config_path()) -> "AzureConfig":
        if not path.exists():
            raise ConfigError("No config found")
        with open(path) as f:
            return cls.deserialize_yaml(f.read())

    def save(self, path: Path = get_config_path()):
        with open(path, "w+") as f:
            f.write(self.serialize_yaml())


omitted = object()


class AzureConfigurator(Configurator):
    NAME = "azure"

    def parse_args(self, args: List = []):
        pass

    def get_config(self, data: Dict) -> BackendConfig:
        return AzureConfig.deserialize(data=data)

    def configure_hub(self, data: Dict):
        pass

    def configure_cli(self):
        tenant_id = None
        subscription_id = None
        location = None
        storage_account = None

        # try:
        #     config = AzureConfig.load()
        # except ConfigError:
        #     config = None

        self.credential = DefaultAzureCredential()

        self.tenant_id = self._ask_tenant_id(tenant_id)
        self.subscription_id = self._ask_subscription_id(subscription_id)

        self.location = self._ask_location(location)
        storage_account = self._ask_storage_account(storage_account)

        config = AzureConfig(
            tenant_id=self.tenant_id,
            subscription_id=self.subscription_id,
            location=self.location,
            # resource_group=
        )
        config.save()
        console.print(f"[grey58]OK[/]")

    def _ask_tenant_id(self, default_tenant_id: Optional[str]) -> str:
        subscription_client = SubscriptionClient(credential=self.credential)
        labels = []
        values = []
        tenant: TenantIdDescription
        for tenant in subscription_client.tenants.list():
            labels.append(tenant.tenant_id)
            values.append(tenant.tenant_id)
        value = ask_choice("Choose Azure tenant", labels, values, selected_value=default_tenant_id)
        return value

    def _ask_subscription_id(self, default_subscription_id: Optional[str]) -> str:
        subscription_client = SubscriptionClient(credential=self.credential)
        labels = []
        values = []
        subscription: Subscription
        for subscription in subscription_client.subscriptions.list():
            labels.append(f"{subscription.display_name} {subscription.subscription_id}")
            values.append(subscription.subscription_id)
        value = ask_choice(
            "Choose Azure subscription", labels, values, selected_value=default_subscription_id
        )
        return value

    def _ask_location(self, default_location: Optional[str]) -> str:
        value = ask_choice(
            "Choose Azure location",
            [f"{l[0]} [{l[1]}]" for l in locations],
            [l[1] for l in locations],
            selected_value=default_location,
        )
        return value

    def _ask_storage_account(self, default_storage_account: Optional[str]) -> Tuple[str, str]:
        storage_account_name = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter Storage Account name[/bold]",
            default=default_storage_account,
        )
        client = StorageManagementClient(
            credential=self.credential, subscription_id=self.subscription_id
        )
        for sa in client.storage_accounts.list():
            if sa.name == storage_account_name:
                if sa.location != self.location:
                    console.print(
                        f"[red bold]✗[/red bold] Storage account location is {sa.location}. "
                        f"But you chose {self.location} as location. "
                        f"Please specify a storage account located in {self.location}."
                    )
                resource_group = _get_resource_group_from_resource_id(sa.id)
                return sa.name, resource_group


def _get_resource_group_from_resource_id(resource_id: str) -> str:
    return resource_id.split("/")[4]


def _create_storage_container(
    credential: TokenCredential,
    subscription_id: str,
    resource_group: str,
    storage_account: str,
    name: str,
) -> str:
    client = StorageManagementClient(credential=credential, subscription_id=subscription_id)
    container: BlobContainer = client.blob_containers.create(
        resource_group_name=resource_group,
        account_name=storage_account,
        container_name=name,
        blob_container=BlobContainer(),
    )
    return container.name


def _create_managed_identity(
    credential: TokenCredential,
    subscription_id: str,
    resource_group: str,
    name: str,
    location: str,
) -> str:
    client = ManagedServiceIdentityClient(credential=credential, subscription_id=subscription_id)
    identity: Identity = client.user_assigned_identities.create_or_update(
        resource_group_name=resource_group,
        resource_name=name,
        parameters=Identity(
            location=location,
        ),
    )
    return identity.principal_id


def _create_key_vault(
    credential: TokenCredential,
    tenant_id: str,
    subscription_id: str,
    resource_group: str,
    name: str,
    location: str,
    runner_principal_id: str,
) -> str:
    client = KeyVaultManagementClient(subscription_id=subscription_id, credential=credential)
    vault: Vault = client.vaults.begin_create_or_update(
        resource_group_name=resource_group,
        vault_name=name,
        parameters=VaultCreateOrUpdateParameters(
            location=location,
            properties=VaultProperties(
                tenant_id=tenant_id,
                sku=Sku(
                    family="A",
                    name="standard",
                ),
                access_policies=[
                    AccessPolicyEntry(
                        tenant_id=tenant_id,
                        object_id=runner_principal_id,
                        permissions=Permissions(
                            secrets=[SecretPermissions.GET, SecretPermissions.LIST]
                        ),
                    )
                ],
            ),
        ),
    ).result()
    return vault.properties.vault_uri


class LogsManager:
    def __init__(self, credential: TokenCredential, subscription_id: str):
        self.log_analytics_client = LogAnalyticsManagementClient(
            credential=credential, subscription_id=subscription_id
        )
        self.monitor_client = MonitorManagementClient(
            credential=credential, subscription_id=subscription_id
        )

    def create_workspace(
        self,
        resource_group: str,
        name: str,
        location: str,
    ) -> str:
        workspace: Workspace = self.log_analytics_client.workspaces.begin_create_or_update(
            resource_group_name=resource_group,
            workspace_name=name,
            parameters=Workspace(
                location=location,
            ),
        ).result()
        return workspace.id

    def create_logs_table(
        self,
        resource_group: str,
        workspace_name: str,
        name: str,
    ) -> str:
        table = self.log_analytics_client.tables.begin_create_or_update(
            resource_group_name=resource_group,
            workspace_name=workspace_name,
            table_name=name,
            parameters=Table(
                schema=Schema(
                    name=name,
                    columns=[
                        Column(name="LogName", type=ColumnTypeEnum.STRING),
                        Column(name="JsonPayload", type=ColumnTypeEnum.STRING),
                        Column(name="TimeGenerated", type=ColumnTypeEnum.DATE_TIME),
                    ],
                ),
            ),
        ).result()
        return table.name

    def create_data_collection_endpoint(
        self,
        resource_group: str,
        name: str,
        location: str,
    ) -> str:
        dce: DataCollectionEndpointResource = self.monitor_client.data_collection_endpoints.create(
            resource_group_name=resource_group,
            data_collection_endpoint_name=name,
            body=DataCollectionEndpointResource(
                location=location,
                # SDK needs description to form correct API request
                description="dstack logs dce",
            ),
        )
        return dce.id

    def create_data_collection_rule(
        self,
        resource_group: str,
        workspace_resource_id: str,
        workspace_id: str,
        name: str,
        location: str,
        logs_table: str,
        data_collection_endpoint_id: str,
    ) -> str:
        dcr: DataCollectionRuleResource = self.monitor_client.data_collection_rules.create(
            resource_group_name=resource_group,
            data_collection_rule_name=name,
            body=DataCollectionRuleResource(
                location=location,
                data_collection_endpoint_id=data_collection_endpoint_id,
                destinations=DataCollectionRuleDestinations(
                    log_analytics=[
                        LogAnalyticsDestination(
                            workspace_resource_id=workspace_resource_id,
                            name=workspace_id,
                        )
                    ]
                ),
                data_flows=[
                    DataFlow(
                        streams=[f"Custom-{logs_table}"],
                        destinations=[workspace_id],
                    )
                ],
            ),
        )
        return dcr.id


if __name__ == "__main__":
    # principal_id = _create_managed_identity(
    #     credential=DefaultAzureCredential(),
    #     subscription_id="86e20cc3-8f2f-4258-a416-85ca989d01e8",
    #     resource_group="dstack-2f61531ea0e7-eastus",
    #     name="dstack-2f61531ea0e7-eastus-runner-identity",
    #     location="eastus"
    # )
    # print(principal_id)
    # url = _create_key_vault(
    #     credential=DefaultAzureCredential(),
    #     tenant_id="87f4458a-488e-4d2f-987e-2f61531ea0e7",
    #     subscription_id="86e20cc3-8f2f-4258-a416-85ca989d01e8",
    #     resource_group="dstack-2f61531ea0e7-eastus",
    #     name="dstack-2f61531ea0e7",
    #     location="eastus",
    #     runner_principal_id=principal_id,
    # )
    # print(url)
    # container_name = _create_storage_container(
    #     credential=DefaultAzureCredential(),
    #     subscription_id="86e20cc3-8f2f-4258-a416-85ca989d01e8",
    #     resource_group="dstack-2f61531ea0e7-eastus",
    #     storage_account="dstackteststorageaccount",
    #     name="dstack-2f61531ea0e7-container",
    # )
    # print(container_name)
    logs_manager = LogsManager(
        credential=DefaultAzureCredential(),
        subscription_id="86e20cc3-8f2f-4258-a416-85ca989d01e8",
    )
    # workspace_resource_id = logs_manager.create_workspace(
    #     resource_group="dstack-2f61531ea0e7-eastus",
    #     name="dstack-2f61531ea0e7-eastus-workspace",
    #     location="eastus",
    # )
    # print(workspace_resource_id)
    # table = logs_manager.create_logs_table(
    #     resource_group="dstack-2f61531ea0e7-eastus",
    #     workspace_name="dstack-2f61531ea0e7-eastus-workspace",
    #     name="dstack_logs_CL"
    # )
    # print(table)
    # dce_id = logs_manager.create_data_collection_endpoint(
    #     resource_group="dstack-2f61531ea0e7-eastus",
    #     name="dstack-2f61531ea0e7-dce",
    #     location="eastus"
    # )
    # print(dce_id)
    dcr_id = logs_manager.create_data_collection_rule(
        resource_group="dstack-2f61531ea0e7-eastus",
        workspace_resource_id="/subscriptions/86e20cc3-8f2f-4258-a416-85ca989d01e8/resourceGroups/dstack-2f61531ea0e7-eastus/providers/Microsoft.OperationalInsights/workspaces/dstack-2f61531ea0e7-eastus-workspace",
        workspace_id="170b91d8-b41e-4248-9e98-19ee0fbbc865",
        name="dstack-2f61531ea0e7-dcr",
        location="eastus",
        logs_table="dstack_logs_CL",
        data_collection_endpoint_id="/subscriptions/86e20cc3-8f2f-4258-a416-85ca989d01e8/resourceGroups/dstack-2f61531ea0e7-eastus/providers/Microsoft.Insights/dataCollectionEndpoints/dstack-2f61531ea0e7-dce",
    )
    print(dcr_id)
