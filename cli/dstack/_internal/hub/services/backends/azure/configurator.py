import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid5

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.graphrbac import GraphRbacManagementClient
from azure.graphrbac.models.graph_error_py3 import GraphErrorException
from azure.identity import ClientSecretCredential, DefaultAzureCredential
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
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.resources.models import ResourceGroup
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.storage.models import BlobContainer
from azure.mgmt.storage.models import Sku as StorageSku
from azure.mgmt.storage.models import StorageAccount, StorageAccountCreateParameters
from azure.mgmt.subscription import SubscriptionClient

from dstack._internal.backend.azure import AzureBackend
from dstack._internal.backend.azure import utils as azure_utils
from dstack._internal.backend.azure.config import AzureConfig
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.schemas import (
    AzureBackendConfig,
    AzureBackendConfigWithCreds,
    AzureBackendConfigWithCredsPartial,
    AzureBackendCreds,
    AzureBackendValues,
    BackendElement,
    BackendElementValue,
    BackendMultiElement,
)
from dstack._internal.hub.services.backends.azure.azure_identity_credential_adapter import (
    AzureIdentityCredentialAdapter,
)
from dstack._internal.hub.services.backends.base import BackendConfigError, Configurator

LOCATIONS = [
    ("(US) Central US", "centralus"),
    ("(US) East US, Virginia", "eastus"),
    ("(US) East US 2, Virginia", "eastus2"),
    ("(US) South Central US, Texas", "southcentralus"),
    ("(US) West US 2, Washington", "westus2"),
    ("(US) West US 3, Phoenix", "westus3"),
    ("(Canada) Canada Central, Toronto", "canadacentral"),
    ("(Europe) France Central, Paris", "francecentral"),
    ("(Europe) Germany West Central, Frankfurt", "germanywestcentral"),
    ("(Europe) North Europe, Ireland", "northeurope"),
    ("(Europe) Sweden Central, Gävle", "swedencentral"),
    ("(Europe) UK South, London", "uksouth"),
    ("(Europe) West Europe", "westeurope"),
    ("(Asia Pacific) Southeast Asia, Singapore", "southeastasia"),
    ("(Asia Pacific) East Asia", "eastasia"),
    ("(South America) Brazil South", "brazilsouth"),
]
LOCATION_VALUES = [l[1] for l in LOCATIONS]
DEFAULT_LOCATION = "eastus"


class AzureConfigurator(Configurator):
    NAME = "azure"

    def configure_backend(
        self, backend_config: AzureBackendConfigWithCredsPartial
    ) -> AzureBackendValues:
        backend_values = AzureBackendValues()
        self.credential = DefaultAzureCredential()
        try:
            backend_values.tenant_id = self._get_tenant_id_element(
                selected=backend_config.tenant_id
            )
        except ClientAuthenticationError:
            backend_values.default_credentials = False
        else:
            backend_values.default_credentials = True

        if backend_config.credentials is None:
            return backend_values

        project_credentials = backend_config.credentials.__root__
        if project_credentials.type == "client":
            self.credential = ClientSecretCredential(
                tenant_id=backend_config.tenant_id,
                client_id=project_credentials.client_id,
                client_secret=project_credentials.client_secret,
            )
            try:
                backend_values.tenant_id = self._get_tenant_id_element(
                    selected=backend_config.tenant_id
                )
            except ClientAuthenticationError:
                self._raise_invalid_credentials_error(
                    fields=[
                        ["tenant_id"],
                        ["credentials", "client_id"],
                        ["credentials", "client_secret"],
                    ]
                )
        elif not backend_values.default_credentials:
            self._raise_invalid_credentials_error(fields=[["credentials"]])

        self.tenant_id = backend_values.tenant_id.selected
        if self.tenant_id is None:
            return backend_values
        backend_values.subscription_id = self._get_subscription_id_element(
            selected=backend_config.subscription_id
        )
        self.subscription_id = backend_values.subscription_id.selected
        if self.subscription_id is None:
            return backend_values
        backend_values.storage_account = self._get_storage_account_element(
            selected=backend_config.storage_account
        )
        backend_values.locations = self._get_locations_element(
            selected=backend_config.locations or [DEFAULT_LOCATION],
        )
        return backend_values

    def create_backend(
        self, project_name: str, backend_config: AzureBackendConfigWithCreds
    ) -> Tuple[Dict, Dict]:
        self.tenant_id = backend_config.tenant_id
        self.subscription_id = backend_config.subscription_id
        self.storage_account = backend_config.storage_account
        self.locations = backend_config.locations
        if backend_config.credentials.__root__.type == "client":
            self.credential = ClientSecretCredential(
                tenant_id=backend_config.tenant_id,
                client_id=backend_config.credentials.__root__.client_id,
                client_secret=backend_config.credentials.__root__.client_secret,
            )
        else:
            self.credential = DefaultAzureCredential()
        self.resource_group, self.location = self._get_resource_group_and_location()
        self._create_storage_container()
        self.vault_url = self._create_key_vault()
        self.runner_principal_id = self._create_runner_managed_identity()
        self._create_network_resources()
        self._create_logs_resources()
        self._grant_roles_or_error()
        config_data = {
            "tenant_id": self.tenant_id,
            "subscription_id": self.subscription_id,
            "locations": self.locations,
            "resource_group": self.resource_group,
            "storage_account": self.storage_account,
            "vault_url": self.vault_url,
        }
        auth_data = backend_config.credentials.__root__.dict()
        return config_data, auth_data

    def get_backend_config(
        self, db_backend: DBBackend, include_creds: bool
    ) -> Union[AzureBackendConfig, AzureBackendConfigWithCreds]:
        json_config = json.loads(db_backend.config)
        tenant_id = json_config["tenant_id"]
        subscription_id = json_config["subscription_id"]
        storage_account = json_config["storage_account"]
        locations = json_config.get("locations")
        if locations is None:
            # old location format
            locations = json_config.get("extra_locations", []) + [json_config.get("location")]
        if include_creds:
            auth_config = json.loads(db_backend.auth)
            return AzureBackendConfigWithCreds(
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                storage_account=storage_account,
                locations=locations,
                credentials=AzureBackendCreds.parse_obj(auth_config),
            )
        return AzureBackendConfig(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            storage_account=storage_account,
            locations=locations,
        )

    def get_backend(self, db_backend: DBBackend) -> AzureBackend:
        config_data = json.loads(db_backend.config)
        auth_data = json.loads(db_backend.auth)
        locations = config_data.get("locations")
        if locations is None:
            # old location format
            locations = config_data.get("extra_locations", []) + [config_data.get("location")]
        config = AzureConfig(
            tenant_id=config_data["tenant_id"],
            subscription_id=config_data["subscription_id"],
            resource_group=config_data["resource_group"],
            storage_account=config_data["storage_account"],
            vault_url=config_data["vault_url"],
            locations=locations,
            credentials=auth_data,
        )
        return AzureBackend(config)

    def _raise_invalid_credentials_error(self, fields: Optional[List[List[str]]] = None):
        raise BackendConfigError(
            "Invalid credentials",
            code="invalid_credentials",
            fields=fields,
        )

    def _get_tenant_id_element(self, selected: Optional[str]) -> BackendElement:
        subscription_client = SubscriptionClient(credential=self.credential)
        element = BackendElement(selected=selected)
        tenant_ids = []
        for tenant in subscription_client.tenants.list():
            tenant_ids.append(tenant.tenant_id)
            element.values.append(
                BackendElementValue(value=tenant.tenant_id, label=tenant.tenant_id)
            )
        if selected is not None and selected not in tenant_ids:
            raise BackendConfigError(
                "Invalid tenant_id", code="invalid_tenant_id", fields=[["tenant_id"]]
            )
        if len(tenant_ids) == 1:
            element.selected = tenant_ids[0]
        return element

    def _get_subscription_id_element(self, selected: Optional[str]) -> BackendElement:
        subscription_client = SubscriptionClient(credential=self.credential)
        element = BackendElement(selected=selected)
        subscription_ids = []
        for subscription in subscription_client.subscriptions.list():
            subscription_ids.append(subscription.subscription_id)
            element.values.append(
                BackendElementValue(
                    value=subscription.subscription_id,
                    label=f"{subscription.display_name} ({subscription.subscription_id})",
                )
            )
        if selected is not None and selected not in subscription_ids:
            raise BackendConfigError(
                "Invalid subscription_id",
                code="invalid_subscription_id",
                fields=[["subscription_id"]],
            )
        if len(subscription_ids) == 1:
            element.selected = subscription_ids[0]
        if len(subscription_ids) == 0:
            # Credentials without granted roles don't see any subscriptions
            raise BackendConfigError(
                message="No Azure subscriptions found for provided credentials. Ensure the account has enough permissions.",
                code="not_enough_permissions",
            )
        return element

    def _get_storage_account_element(self, selected: Optional[str]) -> BackendElement:
        client = StorageManagementClient(
            credential=self.credential, subscription_id=self.subscription_id
        )
        element = BackendElement(selected=selected)
        storage_accounts = []
        for sa in client.storage_accounts.list():
            if sa.provisioning_state == "Succeeded":
                storage_accounts.append(sa.name)
                element.values.append(BackendElementValue(value=sa.name, label=sa.name))
        if selected is not None and selected not in storage_accounts:
            raise BackendConfigError(
                "Invalid storage_account",
                code="invalid_storage_account",
                fields=[["storage_account"]],
            )
        if len(storage_accounts) == 1:
            element.selected = storage_accounts[0]
        return element

    def _get_locations_element(self, selected: List[str]) -> BackendMultiElement:
        element = BackendMultiElement()
        for l in LOCATION_VALUES:
            element.values.append(BackendElementValue(value=l, label=l))
        element.selected = selected
        return element

    def _get_resource_group_and_location(self) -> Tuple[str, str]:
        client = StorageManagementClient(
            credential=self.credential, subscription_id=self.subscription_id
        )
        for sa in client.storage_accounts.list():
            if sa.name == self.storage_account:
                return azure_utils.get_resource_group_from_resource_id(sa.id), sa.location

    def _create_storage_container(self) -> str:
        storage_manager = StorageManager(
            credential=self.credential, subscription_id=self.subscription_id
        )
        return storage_manager.create_storage_container(
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

    def _create_network_resources(self):
        def func(location: str):
            network_manager = NetworkManager(
                credential=self.credential, subscription_id=self.subscription_id
            )
            network_manager.create_virtual_network(
                resource_group=self.resource_group,
                location=location,
                name=azure_utils.get_default_network_name(self.storage_account, location),
                subnet_name=azure_utils.get_default_subnet_name(self.storage_account, location),
            )
            network_manager.create_network_security_group(
                resource_group=self.resource_group,
                location=location,
                name=azure_utils.get_default_network_security_group_name(
                    self.storage_account, location
                ),
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            for location in self.locations:
                executor.submit(func, location)

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

    def _grant_roles_or_error(self):
        try:
            self._grant_roles_to_runner_managed_identity()
            self._grant_roles_to_logged_in_user()
        except HttpResponseError as e:
            if e.status_code == 403:
                raise BackendConfigError(
                    "Not enough permissions. The account must have permissions to assign Azure RBAC roles (e.g. be an Owner).",
                    code="not_enough_permissions",
                )
            raise e

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
        # We grant Monitoring reader to runner so that it can get info about DCE and DCR
        roles_manager.grant_monitoring_reader_role(
            resource_group=self.resource_group,
            principal_id=self.runner_principal_id,
        )

    def _grant_roles_to_logged_in_user(self):
        roles_manager = RolesManager(
            credential=self.credential, subscription_id=self.subscription_id
        )

        principal_id, principal_type = self._get_principal_id_type()

        roles_manager.grant_storage_contributor_role(
            resource_group=self.resource_group,
            storage_account=self.storage_account,
            principal_id=principal_id,
            principal_type=principal_type,
        )
        roles_manager.grant_key_vault_administrator_role(
            resource_group=self.resource_group,
            key_vault=azure_utils.get_key_vault_name(self.storage_account),
            principal_id=principal_id,
            principal_type=principal_type,
        )

    def _get_principal_id_type(self) -> Tuple[str, str]:
        users_manager = UsersManager(credential=self.credential, tenant_id=self.tenant_id)

        client_id = None
        principal_id = None
        try:
            client_id = self.credential._client_id
        except AttributeError:
            principal_id = users_manager.get_logged_in_user_principal_id()
            principal_type = "User"

        if principal_id is None:
            if client_id is None:
                client_id = os.getenv("AZURE_CLIENT_ID")
            principal_id = users_manager.get_application_principal_id(client_id=client_id)
            principal_type = "ServicePrincipal"

        return principal_id, principal_type


class ResourceManager:
    def __init__(self, credential: TokenCredential, subscription_id: str):
        self.resource_client = ResourceManagementClient(
            credential=credential, subscription_id=subscription_id
        )

    def create_resource_group(
        self,
        name: str,
        location: str,
    ) -> str:
        resource_group: ResourceGroup = self.resource_client.resource_groups.create_or_update(
            resource_group_name=name,
            parameters=ResourceGroup(
                location=location,
            ),
        )
        return resource_group.name


class StorageManager:
    def __init__(self, credential: TokenCredential, subscription_id: str):
        self.storage_client = StorageManagementClient(
            credential=credential, subscription_id=subscription_id
        )

    def create_storage_account(
        self,
        resource_group: str,
        name: str,
        location: str,
    ):
        storage_account: StorageAccount = self.storage_client.storage_accounts.begin_create(
            resource_group_name=resource_group,
            account_name=name,
            parameters=StorageAccountCreateParameters(
                sku=StorageSku(name="Standard_LRS"),
                kind="BlobStorage",
                location=location,
                access_tier="Hot",
            ),
        ).result()
        return storage_account.name

    def create_storage_container(
        self,
        resource_group: str,
        storage_account: str,
        name: str,
    ) -> str:
        container: BlobContainer = self.storage_client.blob_containers.create(
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


class NetworkManager:
    def __init__(self, credential: TokenCredential, subscription_id: str):
        self.network_client = NetworkManagementClient(
            credential=credential, subscription_id=subscription_id
        )

    def create_virtual_network(
        self,
        resource_group: str,
        name: str,
        subnet_name: str,
        location: str,
    ) -> Tuple[str, str]:
        network: VirtualNetwork = self.network_client.virtual_networks.begin_create_or_update(
            resource_group_name=resource_group,
            virtual_network_name=name,
            parameters=VirtualNetwork(
                location=location,
                address_space=AddressSpace(address_prefixes=["10.0.0.0/16"]),
                subnets=[
                    Subnet(
                        name=subnet_name,
                        address_prefix="10.0.0.0/20",
                    )
                ],
            ),
        ).result()
        return network.name, subnet_name

    def create_network_security_group(
        self,
        resource_group: str,
        location: str,
        name: str,
    ):
        self.network_client.network_security_groups.begin_create_or_update(
            resource_group_name=resource_group,
            network_security_group_name=name,
            parameters=NetworkSecurityGroup(
                location=location,
                security_rules=[
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
                        Column(name="EventID", type=ColumnTypeEnum.STRING),
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
                                name="EventID",
                                type="string",
                            ),
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


class UsersManager:
    def __init__(self, credential: TokenCredential, tenant_id: str):
        self.graph_client = GraphRbacManagementClient(
            credentials=AzureIdentityCredentialAdapter(credential), tenant_id=tenant_id
        )

    def get_logged_in_user_principal_id(self) -> Optional[str]:
        try:
            user = self.graph_client.signed_in_user.get()
            return user.object_id
        except GraphErrorException:
            return None

    def get_application_principal_id(self, client_id: str) -> str:
        principal_id = self.graph_client.applications.get_service_principals_id_by_app_id(
            client_id
        )
        return principal_id.value


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
        principal_type: str = "ServicePrincipal",
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_storage_account_id(
                subscription_id=self.subscription_id,
                resource_group=resource_group,
                storage_account=storage_account,
            ),
            role_assignment_name=uuid5(
                UUID(principal_id), f"Storage {storage_account} contributor"
            ),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#storage-blob-data-contributor
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe",
                principal_id=principal_id,
                principal_type=principal_type,
            ),
        )

    def grant_vm_contributor_role(
        self,
        resource_group: str,
        principal_id: str,
        principal_type: str = "ServicePrincipal",
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_resource_group_id(self.subscription_id, resource_group),
            role_assignment_name=uuid5(UUID(principal_id), f"VM {resource_group} contributor"),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#virtual-machine-contributor
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/9980e02c-c2be-4d73-94e8-173b1dc7cf3c",
                principal_id=principal_id,
                principal_type=principal_type,
            ),
        )

    def grant_secrets_user_role(
        self,
        resource_group: str,
        key_vault: str,
        principal_id: str,
        principal_type: str = "ServicePrincipal",
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_key_vault_id(self.subscription_id, resource_group, key_vault),
            role_assignment_name=uuid5(UUID(principal_id), f"Secrets {key_vault} user"),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#key-vault-secrets-user
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/4633458b-17de-408a-b874-0445c86b69e6",
                principal_id=principal_id,
                principal_type=principal_type,
            ),
        )

    def grant_monitoring_publisher_role(
        self,
        resource_group: str,
        dcr_name: str,
        principal_id: str,
        principal_type: str = "ServicePrincipal",
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_data_collection_rule_id(
                self.subscription_id, resource_group, dcr_name
            ),
            role_assignment_name=uuid5(UUID(principal_id), f"Monitoring {dcr_name} publisher"),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#monitoring-metrics-publisher
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/3913510d-42f4-4e42-8a64-420c390055eb",
                principal_id=principal_id,
                principal_type=principal_type,
            ),
        )

    def grant_monitoring_reader_role(
        self,
        resource_group: str,
        principal_id: str,
        principal_type: str = "ServicePrincipal",
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_resource_group_id(self.subscription_id, resource_group),
            role_assignment_name=uuid5(UUID(principal_id), f"Monitoring {resource_group} reader"),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#monitoring-reader
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/43d0d8ad-25c7-4714-9337-8ba259a9fe05",
                principal_id=principal_id,
                principal_type=principal_type,
            ),
        )

    def grant_key_vault_administrator_role(
        self,
        resource_group: str,
        key_vault: str,
        principal_id: str,
        principal_type: str = "ServicePrincipal",
    ):
        self.authorization_client.role_assignments.create(
            scope=azure_utils.get_key_vault_id(self.subscription_id, resource_group, key_vault),
            role_assignment_name=uuid5(UUID(principal_id), f"Key vault {key_vault} administrator"),
            parameters=RoleAssignmentCreateParameters(
                # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#key-vault-administrator
                role_definition_id=f"/subscriptions/{self.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/00482a5a-887f-4fb3-b363-3b7fe8e74483",
                principal_id=principal_id,
                principal_type=principal_type,
            ),
        )
