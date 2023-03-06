import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import yaml
from rich import print
from rich.prompt import Prompt

from dstack.backend.hub.client import HubClient
from dstack.core.config import BackendConfig, Configurator, get_config_path
from dstack.core.error import ConfigError


class HUBConfig(BackendConfig):
    NAME = "hub"

    def __init__(self):
        super().__init__()
        self.url = os.getenv("DSTACK_HUB_URL") or None
        self.token = os.getenv("DSTACK_HUB_TOKEN") or None

    def load(self, path: Path = get_config_path()):
        if path.exists():
            with path.open() as f:
                config_data = yaml.load(f, Loader=yaml.FullLoader)
                if config_data.get("backend") != self.NAME:
                    raise ConfigError(f"It's not HUB config")
                if config_data.get("url") is None:
                    raise ConfigError(f"For HUB backend:the URL field is required")
                if config_data.get("token") is None:
                    raise ConfigError(f"For HUB backend:the token field is required")
                self.url = config_data.get("url")
                self.token = config_data.get("token")
        else:
            raise ConfigError()

    def save(self, path: Path = get_config_path()):
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        unparse_url = urlparse(url=self.url)
        new_path = unparse_url.path
        if not new_path.endswith("/api/hub/"):
            new_path = "/api/hub" + new_path

        new_url = urlunparse(
            (
                unparse_url.scheme,
                unparse_url.netloc,
                new_path,
                None,
                None,
                None,
            )
        )
        with path.open("w") as f:
            config_data = {
                "backend": self.NAME,
                "url": new_url,
                "token": self.token,
            }
            yaml.dump(config_data, f)


class HubConfigurator(Configurator):
    NAME = "hub"

    def get_config(self, config: Any):
        pass

    def get_backend_client(self, config: Any):
        pass

    def configure_hub(self, config: Any):
        pass

    def parse_args(self, args: list = []):
        if len(args) % 2 != 0:
            raise ConfigError("Arguments must be even")
        config = HUBConfig()
        for idx in range(0, len(args), 2):
            arg = str(args[idx])
            if arg.startswith("--"):
                arg = arg[2:]
            if hasattr(config, arg):
                setattr(config, arg, args[idx + 1])
        config.save()
        print(f"[grey58]OK[/]")

    def configure_cli(self) -> HUBConfig:
        config = HUBConfig()
        try:
            config.load()
        except ConfigError:
            pass
        default_url = config.url
        default_token = config.token

        config.url, config.token = self.ask_new_param(
            default_url=default_url,
            default_token=default_token,
        )
        config.save()
        print(f"[grey58]OK[/]")

    def ask_new_param(self, default_url: str, default_token: str) -> (str, str):
        url = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter HUB URL[/bold]",
            default=default_url,
        )
        token = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter HUB token[/bold]",
            default=default_token,
        )
        if HubClient.validate(url=url, token=token):
            return url, token
        return self.ask_new_param(
            default_url=url,
            default_token=token,
        )
