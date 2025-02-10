import os

from argcomplete import debug
from argcomplete.completers import BaseCompleter

from dstack.api import Client


class BaseProjectCompleter(BaseCompleter):
    """
    A base completer that initializes the API client using the --project option
    from the parsed arguments, otherwise falls back to the DSTACK_PROJECT environment variable).
    """

    def __init__(self):
        super().__init__()

    def get_api(self, parsed_args):
        # TODO: Feedback needed: Refactor this to avoid duplication with APIBaseCommand._register()
        debug("Retrieving API client")
        project = getattr(parsed_args, "project", None)
        if not project:
            project = os.getenv("DSTACK_PROJECT")
        return Client.from_config(project_name=project)


class RunNameCompleter(BaseProjectCompleter):
    def __call__(self, prefix, parsed_args, **kwargs):
        api = self.get_api(parsed_args)
        debug("Fetching run completions")
        try:
            runs = api.runs.list()
            completions = [run.name for run in runs if run.name.startswith(prefix)]
            return completions
        except Exception as e:
            debug("Error fetching run completions: " + str(e))
            return []
