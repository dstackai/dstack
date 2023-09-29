import json
from typing import List, Optional

from azure.core.credentials import TokenCredential
from azure.mgmt import resource as resource_mgmt
from azure.mgmt import subscription as subscription_mgmt
from azure.mgmt.resource.resources.models import ResourceGroup

from dstack._internal.core.backends.azure import AzureBackend, auth
from dstack._internal.core.backends.azure.config import AzureConfig
from dstack._internal.core.errors import BackendAuthError, ServerClientError
from dstack._internal.core.models.backends.azure import (
    AnyAzureConfigInfo,
    AzureConfigInfo,
    AzureConfigInfoWithCreds,
    AzureConfigInfoWithCredsPartial,
    AzureConfigValues,
    AzureCreds,
    AzureStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElement,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    raise_invalid_credentials_error,
)

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
    TYPE: BackendType = BackendType.AZURE

    def get_config_values(self, config: AzureConfigInfoWithCredsPartial) -> AzureConfigValues:
        config_values = AzureConfigValues()
        config_values.default_creds = False
        if config.creds is None:
            return config_values
        try:
            credential, creds_tenant_id = auth.authenticate(config.creds)
        except BackendAuthError:
            raise_invalid_credentials_error(
                fields=[
                    ["creds", "tenant_id"],
                    ["creds", "client_id"],
                    ["creds", "client_secret"],
                ]
            )
        config_values.tenant_id = self._get_tenant_id_element(
            credential=credential,
            selected=config.tenant_id or creds_tenant_id,
        )
        if config_values.tenant_id.selected is None:
            return config_values
        config_values.subscription_id = self._get_subscription_id_element(
            credential=credential,
            selected=config.subscription_id,
        )
        if config_values.subscription_id.selected is None:
            return config_values
        config_values.locations = self._get_locations_element(
            selected=config.locations or [DEFAULT_LOCATION]
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: AzureConfigInfoWithCreds
    ) -> BackendModel:
        credential, _ = auth.authenticate(config.creds)
        resource_group = self._create_resource_group(
            credential=credential,
            subscription_id=config.subscription_id,
            location=DEFAULT_LOCATION,
            project_name=project.name,
        )
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=AzureStoredConfig(
                **AzureConfigInfo.parse_obj(config).dict(),
                resource_group=resource_group,
            ).json(),
            auth=AzureCreds.parse_obj(config.creds).__root__.json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyAzureConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return AzureConfigInfoWithCreds.parse_obj(config)
        return AzureConfigInfo.parse_obj(config)

    def get_backend(self, model: BackendModel) -> AzureBackend:
        config = self._get_backend_config(model)
        return AzureBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> AzureConfig:
        return AzureConfig(
            **json.loads(model.config),
            creds=AzureCreds.parse_raw(model.auth).__root__,
        )

    def _get_tenant_id_element(
        self,
        credential: auth.AzureCredential,
        selected: Optional[str],
    ) -> ConfigElement:
        subscription_client = subscription_mgmt.SubscriptionClient(credential=credential)
        element = ConfigElement(selected=selected)
        tenant_ids = []
        for tenant in subscription_client.tenants.list():
            tenant_ids.append(tenant.tenant_id)
            element.values.append(
                ConfigElementValue(value=tenant.tenant_id, label=tenant.tenant_id)
            )
        if selected is not None and selected not in tenant_ids:
            raise ServerClientError(
                "Invalid tenant_id",
                code="invalid_tenant_id",
                fields=[["tenant_id"]],
            )
        if len(tenant_ids) == 1:
            element.selected = tenant_ids[0]
        return element

    def _get_subscription_id_element(
        self,
        credential: auth.AzureCredential,
        selected: Optional[str],
    ) -> ConfigElement:
        subscription_client = subscription_mgmt.SubscriptionClient(credential=credential)
        element = ConfigElement(selected=selected)
        subscription_ids = []
        for subscription in subscription_client.subscriptions.list():
            subscription_ids.append(subscription.subscription_id)
            element.values.append(
                ConfigElementValue(
                    value=subscription.subscription_id,
                    label=f"{subscription.display_name} ({subscription.subscription_id})",
                )
            )
        if selected is not None and selected not in subscription_ids:
            raise ServerClientError(
                "Invalid subscription_id",
                code="invalid_subscription_id",
                fields=[["subscription_id"]],
            )
        if len(subscription_ids) == 1:
            element.selected = subscription_ids[0]
        if len(subscription_ids) == 0:
            # Credentials without granted roles don't see any subscriptions
            raise ServerClientError(
                message="No Azure subscriptions found for provided credentials. Ensure the account has enough permissions.",
                code="forbidden",
            )
        return element

    def _get_locations_element(self, selected: List[str]) -> ConfigMultiElement:
        element = ConfigMultiElement()
        for l in LOCATION_VALUES:
            element.values.append(ConfigElementValue(value=l, label=l))
        element.selected = selected
        return element

    def _create_resource_group(
        self,
        credential: auth.AzureCredential,
        subscription_id: str,
        location: str,
        project_name: str,
    ) -> str:
        resource_manager = ResourceManager(
            credential=credential,
            subscription_id=subscription_id,
        )
        return resource_manager.create_resource_group(
            name=_get_resource_group_name(project_name),
            location=location,
        )


class ResourceManager:
    def __init__(self, credential: TokenCredential, subscription_id: str):
        self.resource_client = resource_mgmt.ResourceManagementClient(
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


def _get_resource_group_name(project_name: str) -> str:
    return f"dstack-{project_name}"
