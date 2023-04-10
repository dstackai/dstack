from argparse import Namespace

from dstack.api.backend import get_current_remote_backend, get_local_backend
from dstack.api.repo import get_repo
from dstack.api.run import RunNotFoundError, TagNotFoundError, get_tagged_run_name
from dstack.cli.commands import BasicCommand
from dstack.cli.common import console
from dstack.cli.config import config
from dstack.core.error import BackendError, check_config, check_git


class PullCommand(BasicCommand):
    NAME = "pull"
    DESCRIPTION = "Pull artifacts of a remote run"

    def __init__(self, parser):
        super().__init__(parser)

    def register(self):
        self._parser.add_argument(
            "run_name_or_tag_name",
            metavar="(RUN | :TAG)",
            type=str,
            help="A name of a run or a tag",
        )

    @check_config
    @check_git
    def _command(self, args: Namespace):
        repo = get_repo(config.repo_user_config)
        remote_backend = get_current_remote_backend(repo)
        if remote_backend is None:
            console.print(f"No remote backend configured. Run `dstack config`.")
            exit(1)
        try:
            run_name, tag_head = get_tagged_run_name(remote_backend, args.run_name_or_tag_name)
        except TagNotFoundError as e:
            console.print(f"Cannot find the remote tag '{args.run_name_or_tag_name}'")
            exit(1)
        except RunNotFoundError as e:
            console.print(f"Cannot find the remote run '{args.run_name_or_tag_name}'")
            exit(1)

        local_backend = get_local_backend(repo)
        jobs = remote_backend.list_jobs(run_name)

        if tag_head is not None:
            try:
                local_backend.add_tag_from_run(
                    tag_name=tag_head.tag_name,
                    run_name=tag_head.run_name,
                    run_jobs=jobs,
                )
            except BackendError as e:
                print(e)
                exit(1)

        remote_backend.download_run_artifact_files(
            run_name=run_name,
            output_dir=local_backend.get_artifacts_path(),
        )

        for job in jobs:
            local_backend.create_job(job)

        console.print("Pull completed")
