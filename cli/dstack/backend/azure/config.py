import json
import re
from inspect import signature
from pathlib import Path
from typing import Dict, List

import yaml
from azure.identity import DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.subscription.models import Subscription, TenantIdDescription
from pydantic.error_wrappers import ValidationError
from pydantic.fields import Field
from pydantic.main import create_model
from pydantic.networks import stricturl
from pydantic.tools import parse_obj_as
from pydantic.types import constr
from rich.prompt import Prompt

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


class ModelMeta(type(BackendConfig)):
    def __new__(mcs, name, bases, namespace, **kwargs):
        init = signature(namespace["__init__"])
        parameters = iter(init.parameters.items())
        # skip self.
        next(parameters)
        fields = {
            name: (
                parameter.annotation,
                parameter.default if parameter.default is not parameter.empty else ...,
            )
            for name, parameter in parameters
        }
        Config = create_model(
            f"{name}Model",
            __config__=type("Config", (), {"orm_mode": True}),
            **{"backend": (str, Field(default=namespace["NAME"])), **fields},
        )
        new_namespace = {**namespace, "__model__": Config}
        return super().__new__(mcs, name, bases, new_namespace, **kwargs)


class AzureConfig(BackendConfig, metaclass=ModelMeta):
    NAME = "azure"

    def __init__(
        self,
        subscription_id: str,
        tenant_id: str,
        location: str,
        secret_url: stricturl(allowed_schemes={"https"}),
        secret_resource_group: str,
        storage_url: stricturl(allowed_schemes={"https"}),
        storage_container: str,
    ):
        self.subscription_id = subscription_id
        self.tenant_id = tenant_id
        self.location = location
        self.secret_url = secret_url
        self.secret_vault = secret_url.host.split(".", 1)[0]
        self.secret_resource_group = secret_resource_group
        self.storage_url = storage_url
        self.storage_account = storage_url.host.split(".", 1)[0]
        self.storage_container = storage_container
        self.resource_group = "dstackResourceGroup"
        self.network = "dstackNetwork"
        self.subnet = "default"
        self.managed_identity = "dstackManagedIdentity"

    def save(self, path: Path = get_config_path()):
        with open(path, "w+") as f:
            f.write(self.serialize_yaml())

    def serialize_yaml(self) -> str:
        return yaml.dump(self.serialize())

    def serialize(self) -> Dict:
        # XXX: this is a suboptimal way.
        return json.loads(self.__class__.__model__.from_orm(self).json())

    @classmethod
    def deserialize_yaml(cls, yaml_content: str) -> "AzureConfig":
        content = yaml.load(yaml_content, yaml.FullLoader)
        if content is None:
            raise ConfigError("Cannot load config")
        return cls.deserialize(content)

    @classmethod
    def load(cls, path: Path = get_config_path()):
        if not path.exists():
            raise ConfigError("No config found")
        with open(path) as f:
            return cls.deserialize_yaml(f.read())

    @classmethod
    def deserialize(cls, data: Dict) -> "AzureConfig":
        try:
            config = cls.__model__(**data)
        except ValidationError as e:
            raise ConfigError(f"Parsing config data failed with {e!r}.")
        if config.backend != cls.NAME:
            raise ConfigError(f"It's not Azure config. It's {config.backend!r}.")
        return cls(**config.dict(exclude={"backend"}))


omitted = object()


class AzureConfigurator(Configurator):
    # XXX: duplicate name from AzureBackend.
    # XXX: duplicate name from AzureConfig.
    NAME = "azure"

    def parse_args(self, args: List = []):
        pass

    def get_config(self, data: Dict) -> BackendConfig:
        return AzureConfig.deserialize(data=data)

    def configure_hub(self, data: Dict):
        pass

    def configure_cli(self):
        defaults = {}
        try:
            # XXX: signature of Configurator.load requires to return whole valid config.
            # Which forbids to do recover some data and to use it as defaults.
            config = AzureConfig.load()
        except ConfigError:
            pass

        else:
            defaults = AzureConfig.__model__.from_orm(config).dict()

        subscription_id = self._ask_subscription_id(defaults.get("subscription_id", omitted))
        tenant_id = self._ask_tenant_id(defaults.get("tenant_id", omitted))
        location = self._ask_location(defaults.get("location", omitted))
        secret_url = self._ask_secret_url(defaults.get("secret_url", omitted))
        secret_resource_group = self._ask_secret_resource_group(
            defaults.get("secret_resource_group", omitted)
        )
        storage_url = self._ask_storage_url(defaults.get("storage_url", omitted))
        storage_container = self._ask_storage_container(defaults.get("storage_container", omitted))

        config = AzureConfig.deserialize(
            data={
                "subscription_id": subscription_id,
                "tenant_id": tenant_id,
                "location": location,
                "secret_url": secret_url,
                "secret_resource_group": secret_resource_group,
                "storage_url": storage_url,
                "storage_container": storage_container,
            }
        )
        config.save()
        console.print(f"[grey58]OK[/]")

    def _ask_subscription_id(self, default):
        credential = DefaultAzureCredential()
        subscription_client = SubscriptionClient(credential)
        labels = []
        values = []
        subscription: Subscription
        for subscription in subscription_client.subscriptions.list():
            labels.append(f"{subscription.display_name} {subscription.subscription_id}")
            values.append(subscription.subscription_id)
        if default is omitted:
            default = None
        value = ask_choice("Choose Azure subscription", labels, values, selected_value=default)
        return value

    def _ask_tenant_id(self, default):
        credential = DefaultAzureCredential()
        subscription_client = SubscriptionClient(credential)
        labels = []
        values = []
        tenant: TenantIdDescription
        for tenant in subscription_client.tenants.list():
            labels.append(tenant.tenant_id)
            values.append(tenant.tenant_id)
        if default is omitted:
            default = None
        value = ask_choice("Choose Azure Tenant", labels, values, selected_value=default)
        return value

    def _ask_location(self, default):
        if default is omitted:
            default = None
        value = ask_choice(
            "Choose Azure location",
            [f"{l[0]} [{l[1]}]" for l in locations],
            [l[1] for l in locations],
            selected_value=default,
        )
        return value

    def _ask_secret_url(self, default):
        kwargs = {"default": default} if default is not omitted else {}
        type_ = AzureConfig.__model__.__fields__["secret_url"].type_
        while True:
            secret_url = Prompt.ask(
                "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter Key Vault url[/bold]",
                **kwargs,
            )
            try:
                secret_url_parsed = parse_obj_as(type_, secret_url)
            except ValidationError as e:
                console.print(f"Url is not valid. Errors:")
                for error in e.errors():
                    console.print(f" - {error['msg']}")
                continue
            vault_name, suffix = secret_url_parsed.host.split(".", 1)
            if suffix not in vault_dns_suffixes:
                console.print(
                    f"Suffix {suffix!r} should be from list {', '.join(sorted(vault_dns_suffixes))}."
                )
                continue

            return secret_url_parsed

    def _ask_secret_resource_group(self, default):
        kwargs = {"default": default} if default is not omitted else {}
        type_ = group_name_validator
        while True:
            secret_resource_group = Prompt.ask(
                "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter Key Vault's resource group[/bold]",
                **kwargs,
            )
            try:
                secret_resource_group_parsed = parse_obj_as(type_, secret_resource_group)
            except ValidationError as e:
                console.print(f"Resource group's name is not valid. Errors:")
                for error in e.errors():
                    console.print(f" - {error['msg']}")
                continue

            return secret_resource_group_parsed

    def _ask_storage_url(self, default):
        kwargs = {"default": default} if default is not omitted else {}
        type_ = AzureConfig.__model__.__fields__["storage_url"].type_
        while True:
            secret_url = Prompt.ask(
                "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter Blob Storage url[/bold]",
                **kwargs,
            )
            try:
                storage_url_parsed = parse_obj_as(type_, secret_url)
            except ValidationError as e:
                console.print(f"Url is not valid. Errors:")
                for error in e.errors():
                    console.print(f" - {error['msg']}")
                continue
            vault_name, suffix = storage_url_parsed.host.split(".", 1)
            if suffix not in blob_dns_suffixes:
                console.print(
                    f"Suffix {suffix!r} should be from list {', '.join(sorted(blob_dns_suffixes))}."
                )
                continue

            return storage_url_parsed

    def _ask_storage_container(self, default):
        kwargs = {"default": default} if default is not omitted else {}
        type_ = AzureConfig.__model__.__fields__["storage_container"].type_
        while True:
            secret_url = Prompt.ask(
                "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter Blob Storage container[/bold]",
                **kwargs,
            )
            try:
                storage_container = parse_obj_as(type_, secret_url)
            except ValidationError as e:
                console.print(f"Url is not valid. Errors:")
                for error in e.errors():
                    console.print(f" - {error['msg']}")
                continue

            return storage_container
