from argparse import Namespace
from pathlib import Path

from dstack.api.backend import get_current_remote_backend, get_local_backend
from dstack.api.repos import load_repo
from dstack.api.run import RunNotFoundError, TagNotFoundError, get_tagged_run_name
from dstack.cli.commands import BasicCommand
from dstack.cli.common import check_backend, check_config, check_git, check_init, console
from dstack.cli.config import config
from dstack.core.error import BackendError


class PushCommand(BasicCommand):
    NAME = "push"
    DESCRIPTION = "Push artifacts of a local run"

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
    @check_backend
    @check_init
    def _command(self, args: Namespace):
        repo = load_repo(config.repo_user_config)
        local_backend = get_local_backend(repo)
        remote_backend = get_current_remote_backend(repo)
        if remote_backend is None:
            console.print(f"No remote backend configured. Run `dstack config`.")
            exit(1)

        try:
            run_name, tag_head = get_tagged_run_name(local_backend, args.run_name_or_tag_name)
        except TagNotFoundError as e:
            console.print(f"Cannot find the local tag '{args.run_name_or_tag_name}'")
            exit(1)
        except RunNotFoundError as e:
            console.print(f"Cannot find the local run '{args.run_name_or_tag_name}'")
            exit(1)

        jobs = local_backend.list_jobs(run_name)

        if tag_head is not None:
            try:
                remote_backend.add_tag_from_run(
                    tag_name=tag_head.tag_name,
                    run_name=tag_head.run_name,
                    run_jobs=jobs,
                )
            except BackendError as e:
                print(e)
                exit(1)

        run_artifacts = local_backend.list_run_artifact_files(run_name=run_name)

        for artifact in run_artifacts:
            remote_backend.upload_job_artifact_files(
                job_id=artifact.job_id,
                artifact_name=artifact.name,
                artifact_path=artifact.path,
                local_path=Path(
                    local_backend.get_artifacts_path(),
                    artifact.job_id,
                    artifact.path,
                ),
            )

        for job in jobs:
            remote_backend.create_job(job)

        console.print("Push completed")
