import sys
from typing import Tuple, Optional

from argparse import Namespace

from dstack.core.error import check_config, check_git, BackendError
from dstack.core.tag import TagHead
from dstack.cli.commands import BasicCommand
from dstack.api.repo import load_repo_data
from dstack.api.backend import get_current_remote_backend, get_local_backend


def _get_tagged_run_name(repo_data, backend, args) -> Tuple[str, Optional[TagHead]]:
    if args.run_name_or_tag_name.startswith(":"):
        tag_name = args.run_name_or_tag_name[1:]
        tag_head = backend.get_tag_head(repo_data, tag_name)
        if tag_head:
            return tag_head.run_name, tag_head
        else:
            sys.exit(f"Cannot find the remote tag '{tag_name}'")
    else:
        run_name = args.run_name_or_tag_name
        job_heads = backend.list_job_heads(repo_data, run_name)
        if job_heads:
            return run_name, None
        else:
            sys.exit(f"Cannot find the remote run '{run_name}'")


class PullCommand(BasicCommand):
    NAME = "pull"
    DESCRIPTION = "Copy a run and its artifacts from remote to local"

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
        remote_backend = get_current_remote_backend()
        run_name, tag_head = _get_tagged_run_name(repo_data, remote_backend, args)
        local_backend = get_local_backend()
        jobs = remote_backend.list_jobs(repo_data, run_name)

        if tag_head is not None:
            try:
                local_backend.add_tag_from_run(
                    repo_address=repo_data,
                    tag_name=tag_head.tag_name,
                    run_name=tag_head.run_name,
                    run_jobs=jobs,
                )
            except BackendError as e:
                print(e)
                exit(1)

        remote_backend.download_run_artifact_files(
            repo_address=repo_data,
            run_name=run_name,
            output_dir=local_backend.get_artifacts_path(repo_data),
            output_job_dirs=True,
        )

        for job in jobs:
            local_backend.store_job(job)
        print("Pull completed")
