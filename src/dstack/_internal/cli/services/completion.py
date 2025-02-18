import argparse
import os
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional

import argcomplete
from argcomplete.completers import BaseCompleter

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.services.configs import ConfigManager
from dstack.api import Client


class BaseAPINameCompleter(BaseCompleter, ABC):
    """
    Base class for name completers that fetch resource names via the API.
    """

    def __init__(self):
        super().__init__()

    def get_api(self, parsed_args: argparse.Namespace) -> Optional[Client]:
        argcomplete.debug(f"{self.__class__.__name__}: Retrieving API client")
        project = getattr(parsed_args, "project", os.getenv("DSTACK_PROJECT"))
        try:
            return Client.from_config(project_name=project)
        except ConfigurationError as e:
            argcomplete.debug(f"{self.__class__.__name__}: Error initializing API client: {e}")
            return None

    def __call__(self, prefix: str, parsed_args: argparse.Namespace, **kwargs) -> List[str]:
        api = self.get_api(parsed_args)
        if api is None:
            return []

        argcomplete.debug(f"{self.__class__.__name__}: Fetching completions")
        try:
            resource_names = self.fetch_resource_names(api)
            return [name for name in resource_names if name.startswith(prefix)]
        except Exception as e:
            argcomplete.debug(
                f"{self.__class__.__name__}: Error fetching resource completions: {e}"
            )
            return []

    @abstractmethod
    def fetch_resource_names(self, api: Client) -> Iterable[str]:
        """
        Returns an iterable of resource names.
        """
        pass


class RunNameCompleter(BaseAPINameCompleter):
    def __init__(self, all: bool = False):
        super().__init__()
        self.all = all

    def fetch_resource_names(self, api: Client) -> Iterable[str]:
        return [r.name for r in api.runs.list(self.all)]


class FleetNameCompleter(BaseAPINameCompleter):
    def fetch_resource_names(self, api: Client) -> Iterable[str]:
        return [r.name for r in api.client.fleets.list(api.project)]


class VolumeNameCompleter(BaseAPINameCompleter):
    def fetch_resource_names(self, api: Client) -> Iterable[str]:
        return [r.name for r in api.client.volumes.list(api.project)]


class GatewayNameCompleter(BaseAPINameCompleter):
    def fetch_resource_names(self, api: Client) -> Iterable[str]:
        return [r.name for r in api.client.gateways.list(api.project)]


class ProjectNameCompleter(BaseCompleter):
    """
    Completer for local project names.
    """

    def __call__(self, prefix: str, parsed_args: argparse.Namespace, **kwargs) -> List[str]:
        argcomplete.debug(f"{self.__class__.__name__}: Listing projects from ConfigManager")
        projects = ConfigManager().list_projects()
        return [p for p in projects if p.startswith(prefix)]
