import json
import re
from pathlib import Path

import yaml
from pydantic.error_wrappers import ValidationError
from pydantic.fields import Field
from pydantic.main import BaseModel
from pydantic.networks import stricturl
from pydantic.tools import parse_obj_as
from pydantic.types import constr
from rich import print
from rich.prompt import Confirm, Prompt

from dstack.cli.common import ask_choice
from dstack.core.config import BackendConfig, get_config_path
from dstack.core.error import ConfigError


class Secret(BaseModel):
    url: stricturl(allowed_schemes={"https"})


class Storage(BaseModel):
    url: stricturl(allowed_schemes={"https"})
    container: str


class Config(BaseModel):
    secret: Secret
    storage: Storage
    location: str
    subscription_id: str
    backend: str = Field(default="azure")


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
    # XXX: duplicate name from AzureBackend.
    # XXX: duplicate name from Config.
    NAME = "azure"
    # XXX: this is flag for availability for using in command `config`.
    _configured = True

    config: Config = None

    def save(self, path: Path = get_config_path()):
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        with path.open("w") as f:
            # XXX: this is overhead.
            yaml.dump(json.loads(self.config.json()), f)

    def load(self, path: Path = get_config_path()):
        path = path.resolve()
        if not path.exists():
            raise ConfigError(f"Path {path!r} does not exist.")
        with path.open() as f:
            config_data = yaml.load(f, Loader=yaml.FullLoader)
            if not isinstance(config_data, dict):
                raise ConfigError(
                    f"Shape of data {type(config_data)!r} is not dict from {path!r}."
                )
            try:
                config = Config(**config_data)
            except ValidationError as e:
                raise ConfigError(f"Parsing config data failed with {e!r} from {path!r}.")
            if config.backend != self.NAME:
                raise ConfigError(f"It's not Azure config. It's {config.backend!r} in {path!r}.")
            self.config = config

    def configure(self):
        try:
            self.load()
        except ConfigError:
            pass

        default_secret_url = {}
        default_storage_url = {}
        default_storage_container = {"default": "dstack"}
        if self.config is not None:
            default_secret_url["default"] = self.config.secret.url
            default_storage_url["default"] = self.config.storage.url
            default_storage_container["default"] = self.config.storage.container

        while True:
            secret_url = Prompt.ask(
                "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter Key Vault url[/bold]",
                **default_secret_url,
            )
            # XXX: It is copy-paste from Security.url type annotation.
            try:
                secret_url_parsed = parse_obj_as(stricturl(allowed_schemes={"https"}), secret_url)
            except ValidationError as e:
                print(f"Url is not valid. Errors are {e!r}.")
                continue
            vault_name, suffix = secret_url_parsed.host.split(".", 1)
            if suffix not in vault_dns_suffixes:
                print(
                    f"Suffix {suffix!r} should be from list {', '.join(sorted(vault_dns_suffixes))}."
                )
                continue

            break

        while True:
            storage_url = Prompt.ask(
                "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter Blob Storage url[/bold]",
                **default_storage_url,
            )
            # XXX: It is copy-paste from Storage.url type annotation.
            try:
                storage_url_parsed = parse_obj_as(
                    stricturl(allowed_schemes={"https"}), storage_url
                )
            except ValidationError as e:
                print(f"Url is not valid. Errors are {e!r}.")
                continue
            storage_account_name, suffix = storage_url_parsed.host.split(".", 1)
            if suffix not in blob_dns_suffixes:
                print(
                    f"Suffix {suffix!r} should be from list {', '.join(sorted(blob_dns_suffixes))}."
                )
                continue

            break

        while True:
            storage_container = Prompt.ask(
                "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter Blob Storage container[/bold]",
                **default_storage_container,
            )
            try:
                storage_container_parsed = parse_obj_as(container_validator, storage_container)
            except ValidationError as e:
                print(f"Url is not valid. Errors are {e!r}.")
                continue

            break

        location = ask_choice(
            "Choose Azure location",
            [f"{l[0]} [{l[1]}]" for l in locations],
            [l[1] for l in locations],
            None,
        )

        config_data = {
            "secret": {
                "url": secret_url_parsed,
            },
            "storage": {
                "url": storage_url_parsed,
                "container": storage_container_parsed,
            },
            "location": location,
        }

        self.config = Config(**config_data)
        self.save()
