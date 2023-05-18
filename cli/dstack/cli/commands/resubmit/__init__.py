from argparse import Namespace

from dstack.api.backend import list_backends
from dstack.api.repo import load_repo_data
from dstack.api.run import RunNotFoundError, TagNotFoundError, get_tagged_run_name
from dstack.cli.commands import BasicCommand
from dstack.cli.common import console
from dstack.core.error import check_config, check_git


class ResubmitCommand(BasicCommand):
    NAME = "resubmit"
    DESCRIPTION = ""

    def __init__(self, parser):
        super().__init__(parser)

    def register(self):
        self._parser.add_argument(
            "run_name_or_tag_name",
            metavar="RUN | :TAG",
            type=str,
            help="A name of a run or a tag",
        )

    @check_config
    @check_git
    def _command(self, args: Namespace):
        repo_data = load_repo_data()
        backends = list_backends()
        run_name = None
        backend = None
        for backend in backends:
            try:
                run_name, _ = get_tagged_run_name(repo_data, backend, args.run_name_or_tag_name)
                break
            except (TagNotFoundError, RunNotFoundError):
                pass

        if run_name is None:
            console.print(f"Cannot find the run or tag '{args.run_name_or_tag_name}'")
            exit(1)

        print(backend.list_repo_heads())
        return

        jobs = backend.list_jobs(repo_data, run_name)
        for job in jobs:
            backend.resubmit_job(job)
