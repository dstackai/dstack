import os
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml
from rich import print
from rich.prompt import Prompt
from rich_argparse import RichHelpFormatter

from dstack.backend.hub.client import HubClient
from dstack.core.config import BackendConfig, Configurator, get_config_path
from dstack.core.error import ConfigError


class HUBConfig(BackendConfig):
    NAME = "hub"

    def __init__(self):
        super().__init__()
        self.url = os.getenv("DSTACK_HUB_URL") or None
        self.project = os.getenv("DSTACK_HUB_PROJECT") or None
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
                if config_data.get("project") is None:
                    raise ConfigError(f"For HUB backend:the project field is required")
                self.url = config_data.get("url")
                self.project = config_data.get("project")
                self.token = config_data.get("token")
        else:
            raise ConfigError()

    def save(self, path: Path = get_config_path()):
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        with path.open("w") as f:
            config_data = {
                "backend": self.NAME,
                "url": self.url,
                "project": self.project,
                "token": self.token,
            }
            yaml.dump(config_data, f)


class HubConfigurator(Configurator):
    NAME = "hub"

    def get_config_from_hub_config_data(self, config_data: Any, auth_data: Dict) -> BackendConfig:
        pass

    def get_backend_client(self, config: Any):
        pass

    def configure_hub(self, config: Any):
        pass

    def configure_cli(self) -> HUBConfig:
        config = HUBConfig()
        try:
            config.load()
        except ConfigError:
            pass
        default_url = config.url
        default_token = config.token
        default_project = config.project

        config.url, config.token = self.ask_new_param(
            default_url=default_url,
            default_project=default_project,
            default_token=default_token,
        )
        config.save()
        print(f"[grey58]OK[/]")

    def ask_new_param(
        self, default_url: str, default_project: str, default_token: str
    ) -> Tuple[str, str, str]:
        url = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter HUB URL[/bold]",
            default=default_url,
        )
        project = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter HUB project[/bold]",
            default=default_project,
        )
        token = Prompt.ask(
            "[sea_green3 bold]?[/sea_green3 bold] [bold]Enter HUB token[/bold]",
            default=default_token,
        )
        if HubClient.validate(url=url, project=project, token=token):
            return url, project, token
        return self.ask_new_param(
            default_url=url,
            default_project=project,
            default_token=token,
        )

    def register_parser(self, parser):
        hub_parser = parser.add_parser("hub", help="", formatter_class=RichHelpFormatter)
        hub_parser.add_argument("--url", type=str, help="", required=True)
        hub_parser.add_argument("--project", type=str, help="", required=True)
        hub_parser.add_argument("--token", type=str, help="", required=True)
        hub_parser.set_defaults(func=self._command)

    def _command(self, args: Namespace):
        config = HUBConfig()
        config.url = args.url
        config.project = args.project
        config.token = args.token
        config.save()
        print(f"[grey58]OK[/]")
