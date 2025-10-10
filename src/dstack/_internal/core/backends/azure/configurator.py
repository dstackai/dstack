import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

import azure.core.exceptions
from azure.core.credentials import TokenCredential
from azure.mgmt import msi as msi_mgmt
from azure.mgmt import network as network_mgmt
from azure.mgmt import resource as resource_mgmt
from azure.mgmt import subscription as subscription_mgmt
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
from azure.mgmt.resource.resources.models import ResourceGroup

from dstack._internal.core.backends.azure import auth, compute, resources
from dstack._internal.core.backends.azure import utils as azure_utils
from dstack._internal.core.backends.azure.backend import AzureBackend
from dstack._internal.core.backends.azure.models import (
    AzureBackendConfig,
    AzureBackendConfigWithCreds,
    AzureClientCreds,
    AzureConfig,
    AzureCreds,
    AzureDefaultCreds,
    AzureStoredConfig,
)
from dstack._internal.core.backends.base.configurator import (
    TAGS_MAX_NUM,
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.errors import (
    BackendAuthError,
    BackendError,
    ServerClientError,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
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
LOCATION_VALUES = [loc[1] for loc in LOCATIONS]
DEFAULT_LOCATIONS = LOCATION_VALUES
MAIN_LOCATION = "eastus"


class AzureConfigurator(
    Configurator[
        AzureBackendConfig,
        AzureBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.AZURE
    BACKEND_CLASS = AzureBackend

    def validate_config(self, config: AzureBackendConfigWithCreds, default_creds_enabled: bool):
        if isinstance(config.creds, AzureDefaultCreds) and not default_creds_enabled:
            raise_invalid_credentials_error(fields=[["creds"]])
        if isinstance(config.creds, AzureClientCreds):
            self._set_client_creds_tenant_id(config.creds, config.tenant_id)
        try:
            credential, _ = auth.authenticate(config.creds)
        except BackendAuthError:
            if isinstance(config.creds, AzureClientCreds):
                raise_invalid_credentials_error(
                    fields=[
                        ["creds", "tenant_id"],
                        ["creds", "client_id"],
                        ["creds", "client_secret"],
                    ]
                )
            else:
                raise_invalid_credentials_error(fields=[["creds"]])
        self._check_config_tenant_id(config=config, credential=credential)
        self._check_config_subscription_id(config=config, credential=credential)
        self._check_config_locations(config)
        self._check_config_tags(config)
        self._check_config_resource_group(config=config, credential=credential)
        self._check_config_vm_managed_identity(config=config, credential=credential)
        self._check_config_vpc(config=config, credential=credential)

    def create_backend(
        self, project_name: str, config: AzureBackendConfigWithCreds
    ) -> BackendRecord:
        if config.regions is None:
            config.regions = DEFAULT_LOCATIONS
        if isinstance(config.creds, AzureClientCreds):
            self._set_client_creds_tenant_id(config.creds, config.tenant_id)
        credential, _ = auth.authenticate(config.creds)
        if config.resource_group is None:
            config.resource_group = self._create_resource_group(
                credential=credential,
                subscription_id=config.subscription_id,
                location=MAIN_LOCATION,
                project_name=project_name,
            )
        self._create_network_resources(
            credential=credential,
            subscription_id=config.subscription_id,
            resource_group=config.resource_group,
            locations=config.regions,
            create_default_network=config.vpc_ids is None,
        )
        return BackendRecord(
            config=AzureStoredConfig(
                **AzureBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=AzureCreds.parse_obj(config.creds).__root__.json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> AzureBackendConfigWithCreds:
        config = self._get_config(record)
        return AzureBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> AzureBackendConfig:
        config = self._get_config(record)
        return AzureBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> AzureBackend:
        config = self._get_config(record)
        return AzureBackend(config=config)

    def _get_config(self, record: BackendRecord) -> AzureConfig:
        config_dict = json.loads(record.config)
        regions = config_dict.pop("regions", None)
        if regions is None:
            # Legacy config stores regions as locations
            regions = config_dict.pop("locations")
        return AzureConfig.__response__(
            **config_dict,
            regions=regions,
            creds=AzureCreds.parse_raw(record.auth).__root__,
        )

    def _check_config_tenant_id(
        self, config: AzureBackendConfigWithCreds, credential: auth.AzureCredential
    ):
        subscription_client = subscription_mgmt.SubscriptionClient(credential=credential)
        tenant_ids = []
        for tenant in subscription_client.tenants.list():
            tenant_ids.append(tenant.tenant_id)
        if config.tenant_id not in tenant_ids:
            raise ServerClientError(
                "Invalid tenant_id",
                fields=[["tenant_id"]],
            )

    def _check_config_subscription_id(
        self, config: AzureBackendConfigWithCreds, credential: auth.AzureCredential
    ):
        subscription_client = subscription_mgmt.SubscriptionClient(credential=credential)
        subscription_ids = []
        for subscription in subscription_client.subscriptions.list():
            subscription_ids.append(subscription.subscription_id)
        if config.subscription_id not in subscription_ids:
            raise ServerClientError(
                "Invalid subscription_id",
                fields=[["subscription_id"]],
            )
        if len(subscription_ids) == 0:
            # Credentials without granted roles don't see any subscriptions
            raise ServerClientError(
                msg="No Azure subscriptions found for provided credentials. Ensure the account has enough permissions.",
            )

    def _check_config_locations(self, config: AzureBackendConfigWithCreds):
        if config.regions is None:
            return
        for location in config.regions:
            if location not in LOCATION_VALUES:
                raise ServerClientError(f"Unknown Azure location {location}")

    def _check_config_tags(self, config: AzureBackendConfigWithCreds):
        if not config.tags:
            return
        if len(config.tags) > TAGS_MAX_NUM:
            raise ServerClientError(
                f"Maximum number of tags exceeded. Up to {TAGS_MAX_NUM} tags is allowed."
            )
        try:
            resources.validate_tags(config.tags)
        except BackendError as e:
            raise ServerClientError(e.args[0])

    def _check_config_resource_group(
        self, config: AzureBackendConfigWithCreds, credential: auth.AzureCredential
    ):
        if config.resource_group is None:
            return
        resource_manager = ResourceManager(
            credential=credential,
            subscription_id=config.subscription_id,
        )
        if not resource_manager.resource_group_exists(config.resource_group):
            raise ServerClientError(f"Resource group {config.resource_group} not found")

    def _check_config_vpc(
        self, config: AzureBackendConfigWithCreds, credential: auth.AzureCredential
    ):
        if config.subscription_id is None:
            return None
        allocate_public_ip = config.public_ips if config.public_ips is not None else True
        if config.public_ips is False and config.vpc_ids is None:
            raise ServerClientError(msg="`vpc_ids` must be specified if `public_ips: false`.")
        locations = config.regions
        if locations is None:
            locations = DEFAULT_LOCATIONS
        if config.vpc_ids is not None:
            vpc_ids_locations = list(config.vpc_ids.keys())
            not_configured_locations = [loc for loc in locations if loc not in vpc_ids_locations]
            if len(not_configured_locations) > 0:
                if config.regions is None:
                    raise ServerClientError(
                        f"`vpc_ids` not configured for regions {not_configured_locations}. "
                        "Configure `vpc_ids` for all regions or specify `regions`."
                    )
                raise ServerClientError(
                    f"`vpc_ids` not configured for regions {not_configured_locations}. "
                    "Configure `vpc_ids` for all regions specified in `regions`."
                )
            network_client = network_mgmt.NetworkManagementClient(
                credential=credential,
                subscription_id=config.subscription_id,
            )
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = []
                for location in locations:
                    future = executor.submit(
                        compute.get_resource_group_network_subnet_or_error,
                        network_client=network_client,
                        resource_group=None,
                        vpc_ids=config.vpc_ids,
                        location=location,
                        allocate_public_ip=allocate_public_ip,
                    )
                    futures.append(future)
                for future in as_completed(futures):
                    try:
                        future.result()
                    except BackendError as e:
                        raise ServerClientError(e.args[0])

    def _check_config_vm_managed_identity(
        self, config: AzureBackendConfigWithCreds, credential: auth.AzureCredential
    ):
        try:
            resource_group, identity_name = compute.parse_vm_managed_identity(
                config.vm_managed_identity
            )
        except BackendError as e:
            raise ServerClientError(e.args[0])
        if resource_group is None or identity_name is None:
            return
        msi_client = msi_mgmt.ManagedServiceIdentityClient(credential, config.subscription_id)
        try:
            msi_client.user_assigned_identities.get(resource_group, identity_name)
        except azure.core.exceptions.ResourceNotFoundError:
            raise ServerClientError(
                f"Managed identity {identity_name} not found in resource group {resource_group}"
            )

    def _set_client_creds_tenant_id(
        self,
        creds: AzureClientCreds,
        tenant_id: Optional[str],
    ):
        if creds.tenant_id is not None:
            return
        if tenant_id is None:
            raise_invalid_credentials_error(
                fields=[
                    ["creds", "tenant_id"],
                    ["tenant_id"],
                ]
            )
        creds.tenant_id = tenant_id

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

    def _create_network_resources(
        self,
        credential: auth.AzureCredential,
        subscription_id: str,
        resource_group: str,
        locations: List[str],
        create_default_network: bool,
    ):
        def func(location: str):
            network_manager = NetworkManager(
                credential=credential, subscription_id=subscription_id
            )
            if create_default_network:
                network_manager.create_virtual_network(
                    resource_group=resource_group,
                    location=location,
                    name=azure_utils.get_default_network_name(resource_group, location),
                    subnet_name=azure_utils.get_default_subnet_name(resource_group, location),
                )
            network_manager.create_network_security_group(
                resource_group=resource_group,
                location=location,
                name=azure_utils.get_default_network_security_group_name(resource_group, location),
            )
            network_manager.create_gateway_network_security_group(
                resource_group=resource_group,
                location=location,
                name=azure_utils.get_gateway_network_security_group_name(resource_group, location),
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            for location in locations:
                executor.submit(func, location)


def _get_resource_group_name(project_name: str) -> str:
    return f"dstack-{project_name}"


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

    def resource_group_exists(
        self,
        name: str,
    ) -> bool:
        try:
            self.resource_client.resource_groups.get(
                resource_group_name=name,
            )
        except azure.core.exceptions.ResourceNotFoundError:
            return False
        return True


class NetworkManager:
    def __init__(self, credential: TokenCredential, subscription_id: str):
        self.network_client = network_mgmt.NetworkManagementClient(
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

    def create_gateway_network_security_group(
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
                        name="gateway_all",
                        protocol=SecurityRuleProtocol.TCP,
                        source_address_prefix="Internet",
                        source_port_range="*",
                        destination_address_prefix="*",
                        destination_port_ranges=["22", "80", "443"],
                        access=SecurityRuleAccess.ALLOW,
                        priority=101,
                        direction=SecurityRuleDirection.INBOUND,
                    )
                ],
            ),
        ).result()
