import os

import argcomplete
from argcomplete.completers import BaseCompleter

from dstack._internal.core.services.configs import ConfigManager
from dstack.api import Client


class ResourceNameCompleter(BaseCompleter):
    """
    A resource name completer that initializes the API client using the --project option
    from the parsed arguments, otherwise falls back to the DSTACK_PROJECT environment variable.
    """

    def __init__(self):
        super().__init__()

    def get_api(self, parsed_args):
        argcomplete.debug("Retrieving API client")
        project = getattr(parsed_args, "project", os.getenv("DSTACK_PROJECT"))
        return Client.from_config(project_name=project)


class RunNameCompleter(ResourceNameCompleter):
    def __init__(self, all: bool = False):
        super().__init__()
        self.all = all

    def __call__(self, prefix, parsed_args, **kwargs):
        api = self.get_api(parsed_args)
        argcomplete.debug("Fetching run completions")
        try:
            runs = api.runs.list(self.all)
            completions = [run.name for run in runs if run.name.startswith(prefix)]
            return completions
        except Exception as e:
            argcomplete.debug("Error fetching run completions: " + str(e))
            return [""]


class FleetNameCompleter(ResourceNameCompleter):
    def __call__(self, prefix, parsed_args, **kwargs):
        api = self.get_api(parsed_args)
        argcomplete.debug("Fetching fleet completions")
        try:
            fleets = api.client.fleets.list(api.project)
            completions = [fleet.name for fleet in fleets if fleet.name.startswith(prefix)]
            return completions
        except Exception as e:
            argcomplete.debug("Error fetching fleet completions: " + str(e))
            return [""]


class VolumeNameCompleter(ResourceNameCompleter):
    def __call__(self, prefix, parsed_args, **kwargs):
        api = self.get_api(parsed_args)
        argcomplete.debug("Fetching volume completions")
        try:
            volumes = api.client.volumes.list(api.project)
            completions = [volume.name for volume in volumes if volume.name.startswith(prefix)]
            return completions
        except Exception as e:
            argcomplete.debug("Error fetching volume completions: " + str(e))
            return [""]


class ProjectNameCompleter(ResourceNameCompleter):
    def __call__(self, prefix, parsed_args, **kwargs):
        projects = ConfigManager().list_projects()
        return projects


class GatewayNameCompleter(ResourceNameCompleter):
    def __call__(self, prefix, parsed_args, **kwargs):
        api = self.get_api(parsed_args)
        argcomplete.debug("Fetching gateway completions")
        try:
            gateways = api.client.gateways.list(api.project)
            completions = [gateway.name for gateway in gateways if gateway.name.startswith(prefix)]
            return completions
        except Exception as e:
            argcomplete.debug("Error fetching gateway completions: " + str(e))
            return [""]
