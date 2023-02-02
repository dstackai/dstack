from pathlib import Path

from argparse import Namespace

from dstack.core.error import check_config, check_git, BackendError
from dstack.cli.commands import BasicCommand
from dstack.api.repo import load_repo_data
from dstack.api.backend import get_current_remote_backend, get_local_backend
from dstack.api.run import RunNotFoundError, TagNotFoundError, get_tagged_run_name


class PushCommand(BasicCommand):
    NAME = "push"
    DESCRIPTION = "Copy a run and its artifacts from local to remote"

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
        repo_data = load_repo_data()
        local_backend = get_local_backend()
        try:
            run_name, tag_head = get_tagged_run_name(
                repo_data, local_backend, args.run_name_or_tag_name
            )
        except TagNotFoundError as e:
            print(f"Cannot find the local tag '{args.run_name_or_tag_name}'")
            exit(1)
        except RunNotFoundError as e:
            print(f"Cannot find the local run '{args.run_name_or_tag_name}'")
            exit(1)

        jobs = local_backend.list_jobs(repo_data, run_name)

        remote_backend = get_current_remote_backend()

        if tag_head is not None:
            try:
                remote_backend.add_tag_from_run(
                    repo_address=repo_data,
                    tag_name=tag_head.tag_name,
                    run_name=tag_head.run_name,
                    run_jobs=jobs,
                )
            except BackendError as e:
                print(e)
                exit(1)

        run_artifacts = local_backend.list_run_artifact_files(
            repo_address=repo_data, run_name=run_name
        )

        for job_id, artifact_name, _, _ in run_artifacts:
            remote_backend.upload_job_artifact_files(
                repo_address=repo_data,
                job_id=job_id,
                artifact_name=artifact_name,
                local_path=Path(
                    local_backend.get_artifacts_path(repo_data), job_id, artifact_name
                ),
            )

        for job in jobs:
            remote_backend.store_job(job)

        print("Push completed")
