from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid5

import yaml
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.authorization.models import RoleAssignmentCreateParameters
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.keyvault.models import Sku, Vault, VaultCreateOrUpdateParameters, VaultProperties
from azure.mgmt.loganalytics import LogAnalyticsManagementClient
from azure.mgmt.loganalytics.models import Column, ColumnTypeEnum, Schema, Table, Workspace
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.monitor.models import (
    ColumnDefinition,
    DataCollectionEndpointResource,
    DataCollectionRuleDestinations,
    DataCollectionRuleResource,
    DataFlow,
    LogAnalyticsDestination,
    StreamDeclaration,
)
from azure.mgmt.msi import ManagedServiceIdentityClient
from azure.mgmt.msi.models import Identity
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.models import (
    AddressSpace,
    NetworkSecurityGroup,
    SecurityRule,
    SecurityRuleAccess,
    SecurityRuleDirection,
    SecurityRuleProtocol,
    Subnet,
    VirtualNetwork,
)
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import BlobContainer
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.subscription.models import Subscription, TenantIdDescription
from rich.prompt import Prompt

from dstack.backend.azure import utils as azure_utils
from dstack.cli.common import ask_choice, console
from dstack.core.config import BackendConfig, Configurator, get_config_path
from dstack.core.error import ConfigError

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
        vault_url: str,
        network: str,
        subnet: str,
    ):
        self.subscription_id = subscription_id
        self.tenant_id = tenant_id
        self.location = location
        self.resource_group = resource_group
        self.storage_account = storage_account
        self.vault_url = vault_url
        self.network = network
        self.subnet = subnet

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
            vault_url = data["vault_url"]
            network = data["network"]
            subnet = data["subnet"]
        except KeyError as e:
            raise ConfigError("Cannot load config")

        return cls(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            location=location,
            resource_group=resource_group,
            storage_account=storage_account,
            vault_url=vault_url,
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

        try:
            config = AzureConfig.load()
        except ConfigError:
            pass
        else:
            tenant_id = config.tenant_id
            subscription_id = config.subscription_id
            location = config.location
            storage_account = config.storage_account

        self.credential = DefaultAzureCredential()

        self.tenant_id = self._ask_tenant_id(tenant_id)
        self.subscription_id = self._ask_subscription_id(subscription_id)
        self.location = self._ask_location(location)
        self.storage_account, self.resource_group = self._ask_storage_account(storage_account)

        console.print("Configuring Azure resources...")
        self._create_storage_container()
        self.vault_url = self._create_key_vault()
        self.runner_principal_id = self._create_runner_managed_identity()
        self.network, self.subnet = self._create_network_resources()
        self._create_logs_resources()
        self._grant_roles_to_runner_managed_identity()

        config = AzureConfig(
            tenant_id=self.tenant_id,
            subscription_id=self.subscription_id,
            location=self.location,
            resource_group=self.resource_group,
            storage_account=self.storage_account,
            vault_url=self.vault_url,
            network=self.network,
            subnet=self.subnet,
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
            if subscription.state != "Enabled":
                continue
            labels.append(f"{subscription.display_name} ({subscription.subscription_id})")
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
        # TODO show choice
        storage_account_name = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter Storage Account name[/bold]",
            default=default_storage_account,
        )
        client = StorageManagementClient(
            credential=self.credential, subscription_id=self.subscription_id
        )
        for sa in client.storage_accounts.list():
            if sa.provisioning_state != "Succeeded" or sa.name != storage_account_name:
                continue
            if sa.location != self.location:
                console.print(
                    f"[red bold]✗[/red bold] Storage account location is {sa.location}."
                    f" But you chose {self.location} as location."
                    f" Please specify a storage account located in {self.location}."
                )
                return self._ask_storage_account(default_storage_account)
            console.print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{sa.name}[/grey74]")
            resource_group = azure_utils.get_resource_group_from_resource_id(sa.id)
            return sa.name, resource_group
        console.print(
            f"[red bold]✗[/red bold] Storage account '{storage_account_name}' does not exist."
        )
        return self._ask_storage_account(default_storage_account)

    def _create_storage_container(self) -> str:
        return _create_storage_container(
            credential=self.credential,
            subscription_id=self.subscription_id,
            resource_group=self.resource_group,
            storage_account=self.storage_account,
            name=azure_utils.DSTACK_CONTAINER_NAME,
        )

    def _create_key_vault(self) -> str:
        return _create_key_vault(
            credential=self.credential,
            tenant_id=self.tenant_id,
            subscription_id=self.subscription_id,
            resource_group=self.resource_group,
            location=self.location,
            name=azure_utils.get_key_vault_name(self.storage_account),
        )

    def _create_runner_managed_identity(self) -> str:
        return _create_managed_identity(
            credential=self.credential,
            subscription_id=self.subscription_id,
            resource_group=self.resource_group,
            location=self.location,
            name=azure_utils.get_runner_managed_identity_name(self.storage_account),
        )

    def _grant_roles_to_runner_managed_identity(self) -> str:
        roles_manager = RolesManager(
            credential=self.credential, subscription_id=self.subscription_id
        )
        roles_manager.grant_storage_contributor_role(
            resource_group=self.resource_group,
            storage_account=self.storage_account,
            principal_id=self.runner_principal_id,
        )
        roles_manager.grant_vm_contributor_role(
            resource_group=self.resource_group,
            principal_id=self.runner_principal_id,
        )
        roles_manager.grant_secrets_user_role(
            resource_group=self.resource_group,
            key_vault=azure_utils.get_key_vault_name(self.storage_account),
            principal_id=self.runner_principal_id,
        )
        roles_manager.grant_monitoring_publisher_role(
            resource_group=self.resource_group,
            dcr_name=azure_utils.get_data_collection_rule_name(self.storage_account),
            principal_id=self.runner_principal_id,
        )

    def _create_network_resources(self) -> Tuple[str, str]:
        network_manager = NetworkManager(
            credential=self.credential, subscription_id=self.subscription_id
        )
        network = network_manager.create_virtual_network(
            resource_group=self.resource_group,
            location=self.location,
            name=azure_utils.get_default_network_name(self.storage_account),
        )
        subnet = network_manager.create_subnet(
            resource_group=self.resource_group,
            network=network,
            name=azure_utils.get_default_subnet_name(self.storage_account),
        )
        network_manager.create_network_security_group(
            resource_group=self.resource_group,
            location=self.location,
        )
        return network, subnet

    def _create_logs_resources(self):
        logs_manager = LogsManager(
            credential=self.credential, subscription_id=self.subscription_id
        )
        workspace_name = azure_utils.get_logs_workspace_name(self.storage_account)
        workspace_resource_id = logs_manager.create_workspace(
            resource_group=self.resource_group,
            location=self.location,
            name=workspace_name,
        )
        table_name = logs_manager.create_logs_table(
            resource_group=self.resource_group,
            workspace_name=workspace_name,
            name=azure_utils.DSTACK_LOGS_TABLE_NAME,
        )
        dce_id = logs_manager.create_data_collection_endpoint(
            resource_group=self.resource_group,
            location=self.location,
            name=azure_utils.get_data_collection_endpoint_name(self.storage_account),
        )
        logs_manager.create_data_collection_rule(
            resource_group=self.resource_group,
            workspace_resource_id=workspace_resource_id,
            location=self.location,
            logs_table=table_name,
            data_collection_endpoint_id=dce_id,
            name=azure_utils.get_data_collection_rule_name(self.storage_account),
        )


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


def _create_key_vault(
    credential: TokenCredential,
    tenant_id: str,
    subscription_id: str,
    resource_group: str,
    name: str,
    location: str,
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
                enable_rbac_authorization=True,
            ),
        ),
    ).result()
    return vault.properties.vault_uri


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


class RolesManager:
    def __init__(self, credential: TokenCredential, subscription_id: str):
        self.subscription_id = subscription_id
        self.authorization_client = AuthorizationManagementClient(
            credential=credential, subscription_id=subscription_id
        )

    def grant_storage_contributor_role(
        self,
        resource_group: str,
        storage_account: str,
        principal_id: str,
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_storage_account_id(
                subscription_id=self.subscription_id,
                resource_group=resource_group,
                storage_account=storage_account,
            ),
            role_assignment_name=uuid5(UUID(principal_id), "Storage contributor"),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#storage-blob-data-contributor
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe",
                principal_id=principal_id,
                principal_type="ServicePrincipal",
            ),
        )

    def grant_vm_contributor_role(
        self,
        resource_group: str,
        principal_id: str,
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_resource_group_id(self.subscription_id, resource_group),
            role_assignment_name=uuid5(UUID(principal_id), "VM contributor"),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#virtual-machine-contributor
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/9980e02c-c2be-4d73-94e8-173b1dc7cf3c",
                principal_id=principal_id,
                principal_type="ServicePrincipal",
            ),
        )

    def grant_secrets_user_role(
        self,
        resource_group: str,
        key_vault: str,
        principal_id: str,
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_key_vault_id(self.subscription_id, resource_group, key_vault),
            role_assignment_name=uuid5(UUID(principal_id), "Secrets user"),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#key-vault-secrets-user
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/4633458b-17de-408a-b874-0445c86b69e6",
                principal_id=principal_id,
                principal_type="ServicePrincipal",
            ),
        )

    def grant_monitoring_publisher_role(
        self,
        resource_group: str,
        dcr_name: str,
        principal_id: str,
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_data_collection_rule_id(
                self.subscription_id, resource_group, dcr_name
            ),
            role_assignment_name=uuid5(UUID(principal_id), "Monitoring publisher"),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#monitoring-metrics-publisher
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/3913510d-42f4-4e42-8a64-420c390055eb",
                principal_id=principal_id,
                principal_type="ServicePrincipal",
            ),
        )


class NetworkManager:
    def __init__(self, credential: TokenCredential, subscription_id: str):
        self.network_client = NetworkManagementClient(
            credential=credential, subscription_id=subscription_id
        )

    def create_virtual_network(
        self,
        resource_group: str,
        name: str,
        location: str,
    ):
        network: VirtualNetwork = self.network_client.virtual_networks.begin_create_or_update(
            resource_group_name=resource_group,
            virtual_network_name=name,
            parameters=VirtualNetwork(
                location=location, address_space=AddressSpace(address_prefixes=["10.0.0.0/16"])
            ),
        ).result()
        return network.name

    def create_subnet(
        self,
        resource_group: str,
        network: str,
        name: str,
    ):
        subnet: Subnet = self.network_client.subnets.begin_create_or_update(
            resource_group_name=resource_group,
            virtual_network_name=network,
            subnet_name=name,
            subnet_parameters=Subnet(address_prefix="10.0.0.0/20"),
        ).result()
        return subnet.name

    def create_network_security_group(
        self,
        resource_group: str,
        location: str,
    ):
        self.network_client.network_security_groups.begin_create_or_update(
            resource_group_name=resource_group,
            network_security_group_name=azure_utils.DSTACK_NETWORK_SECURITY_GROUP,
            parameters=NetworkSecurityGroup(
                location=location,
                security_rules=[
                    SecurityRule(
                        name="runner_service",
                        protocol=SecurityRuleProtocol.TCP,
                        source_address_prefix="Internet",
                        source_port_range="*",
                        destination_address_prefix="*",
                        destination_port_range="3000-4000",
                        access=SecurityRuleAccess.ALLOW,
                        priority=101,
                        direction=SecurityRuleDirection.INBOUND,
                    ),
                    SecurityRule(
                        name="runner_ssh",
                        protocol=SecurityRuleProtocol.TCP,
                        source_address_prefix="Internet",
                        source_port_range="*",
                        destination_address_prefix="*",
                        destination_port_range="22",
                        access=SecurityRuleAccess.ALLOW,
                        priority=100,
                        direction=SecurityRuleDirection.INBOUND,
                    ),
                ],
            ),
        ).result()


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
                        Column(name="JsonPayload", type=ColumnTypeEnum.DYNAMIC),
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
        name: str,
        location: str,
        logs_table: str,
        data_collection_endpoint_id: str,
    ) -> str:
        stream_name = f"Custom-{logs_table}"
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
                            name="dstack_logs",
                        )
                    ]
                ),
                data_flows=[
                    DataFlow(
                        streams=[stream_name],
                        destinations=["dstack_logs"],
                        output_stream=stream_name,
                        transform_kql="source",
                    )
                ],
                stream_declarations={
                    stream_name: StreamDeclaration(
                        columns=[
                            ColumnDefinition(
                                name="LogName",
                                type="string",
                            ),
                            ColumnDefinition(
                                name="JsonPayload",
                                type="dynamic",
                            ),
                            ColumnDefinition(name="TimeGenerated", type="datetime"),
                        ]
                    )
                },
            ),
        )
        return dcr.id
