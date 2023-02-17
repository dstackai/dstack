import json
import re
from pathlib import Path

import yaml
from pydantic.error_wrappers import ValidationError
from pydantic.fields import Field
from pydantic.main import BaseModel
from pydantic.networks import stricturl
from pydantic.tools import parse_obj_as
from rich import print
from rich.prompt import Confirm, Prompt

from dstack.core.config import BackendConfig, get_config_path
from dstack.core.error import ConfigError


class Secret(BaseModel):
    url: stricturl(allowed_schemes={"https"})


class Config(BaseModel):
    secret: Secret
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


dns_suffixes = frozenset(
    ("vault.azure.net", "vault.azure.cn", "vault.usgovcloudapi.net", "vault.microsoftazure.de")
)


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
                raise ConfigError(f"It's not Asure config. It's {config.backend!r} in {path!r}.")
            self.config = config

    def configure(self):
        try:
            self.load()
        except ConfigError:
            pass

        default_secret_url = {}
        if self.config is not None:
            default_secret_url["default"] = self.config.secret.url

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
            # https://learn.microsoft.com/en-us/azure/key-vault/general/about-keys-secrets-certificates#dns-suffixes-for-base-url
            vault_name, suffix = secret_url_parsed.host.split(".", 1)
            if suffix not in dns_suffixes:
                print(f"Suffix {suffix!r} should be from list {', '.join(sorted(dns_suffixes))}.")
                continue

            break

        config_data = {
            "secret": {
                "url": secret_url_parsed,
            }
        }

        self.config = Config(**config_data)
        self.save()
