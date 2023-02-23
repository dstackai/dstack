import os
import re
from pathlib import Path
from typing import Optional

import boto3
import yaml
from botocore.client import BaseClient
from rich import print
from rich.prompt import Confirm, Prompt

from dstack.backend.hub.client import HubClient
from dstack.cli.common import _is_termios_available, ask_choice
from dstack.core.config import BackendConfig, get_config_path
from dstack.core.error import ConfigError


class HUBConfig(BackendConfig):
    NAME = "hub"

    _configured = True

    def __init__(self):
        super().__init__()
        self.host = os.getenv("DSTACK_HUB_HOST") or "127.0.0.1"
        self.port = os.getenv("DSTACK_HUB_PORT") or "3000"
        self.token = os.getenv("DSTACK_HUB_TOKEN") or None
        self.hub_name = os.getenv("DSTACK_HUB_NAME") or "test"  # TODO replace

    def load(self, path: Path = get_config_path()):
        if path.exists():
            with path.open() as f:
                config_data = yaml.load(f, Loader=yaml.FullLoader)
                if config_data.get("backend") != self.NAME:
                    raise ConfigError(f"It's not HUB config")
                if config_data.get("token") is None:
                    raise ConfigError(f"For HUB backend:the token field is required")
                self.host = config_data.get("host") or "127.0.0.1"
                self.port = config_data.get("port") or "3000"
                self.token = config_data.get("token")
                self.hub_name = config_data.get("hub_name") or "test"
        else:
            raise ConfigError()

    def save(self, path: Path = get_config_path()):
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        with path.open("w") as f:
            config_data = {
                "backend": self.NAME,
                "host": self.host,
                "token": self.token,
                "hub_name": self.hub_name,
            }
            yaml.dump(config_data, f)

    def configure(self):
        try:
            self.load()
        except ConfigError:
            pass
        default_host = self.host
        default_port = self.port
        default_token = self.token
        default_hub_name = self.hub_name

        self.host, self.port, self.token, self.hub_name = self.ask_new_param(
            default_host=default_host,
            default_port=default_port,
            default_token=default_token,
            default_hub_name=default_hub_name,
        )
        self.save()
        print(f"[grey58]OK[/]")

    def ask_new_param(
        self, default_host: str, default_port: str, default_token: str, default_hub_name: str
    ) -> (str, str, str, str):
        host = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter HUB host name[/bold]",
            default=default_host,
        )
        port = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter HUB host port[/bold]",
            default=default_port,
        )
        token = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter HUB token[/bold]",
            default=default_token,
        )
        hub_name = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter HUB name[/bold]",
            default=default_hub_name,
        )
        if HubClient.validate(host=host, port=port, token=token, hub_name=hub_name):
            return host, port, token
        return self.ask_new_param(
            default_host=host,
            default_port=port,
            default_token=token,
            default_hub_name=default_hub_name,
        )
