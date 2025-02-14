import os

import argcomplete
from argcomplete.completers import BaseCompleter

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.services.configs import ConfigManager
from dstack.api import Client


class APIResourceNameCompleter(BaseCompleter):
    """
    Base class that handles creating the API client and fetching resources.
    Subclasses should implement fetch_resources(api, parsed_args).
    """

    def __init__(self):
        super().__init__()

    def get_api(self, parsed_args):
        argcomplete.debug(f"{self.__class__.__name__}: Retrieving API client")
        project = getattr(parsed_args, "project", os.getenv("DSTACK_PROJECT"))
        try:
            return Client.from_config(project_name=project)
        except ConfigurationError as e:
            argcomplete.debug(f"{self.__class__.__name__}: Error initializing API client: {e}")
            return None

    def fetch_resources(self, api):
        """
        Returns an iterable of objects that have a .name attribute.
        """
        raise NotImplementedError

    def __call__(self, prefix, parsed_args, **kwargs):
        api = self.get_api(parsed_args)
        if not api:
            return []

        argcomplete.debug(f"{self.__class__.__name__}: Fetching completions")
        try:
            resources = self.fetch_resources(api)
            return [r.name for r in resources if r.name.startswith(prefix)]
        except Exception as e:
            argcomplete.debug(
                f"{self.__class__.__name__}: Error fetching resource completions: {e}"
            )
            return []


class RunNameCompleter(APIResourceNameCompleter):
    def __init__(self, all=False):
        super().__init__()
        self.all = all

    def fetch_resources(self, api):
        return api.runs.list(self.all)


class FleetNameCompleter(APIResourceNameCompleter):
    def fetch_resources(self, api):
        return [api.client.fleets.list(api.project)]


class VolumeNameCompleter(APIResourceNameCompleter):
    def fetch_resources(self, api):
        return api.client.volumes.list(api.project)


class GatewayNameCompleter(APIResourceNameCompleter):
    def fetch_resources(self, api):
        return api.client.gateways.list(api.project)


class ProjectNameCompleter(BaseCompleter):
    """
    Completer for local project names.
    """

    def __call__(self, prefix, parsed_args, **kwargs):
        argcomplete.debug(f"{self.__class__.__name__}: Listing projects from ConfigManager")
        projects = ConfigManager().list_projects()
        return [p for p in projects if p.startswith(prefix)]
