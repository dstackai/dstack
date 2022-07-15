import os
from argparse import ArgumentParser
from typing import List, Optional

from dstack import Provider, Job, App
# TODO: Provide job.applications (incl. application name, and query)
from dstack.cli.common import get_jobs


class TensorboardProvider(Provider):
    def __init__(self):
        super().__init__()
        self.app = None
        self.before_run = None
        self.python = None
        self.version = None
        self.run_names = None
        self.logdir = None

    def load(self):
        super()._load(schema="schema.yaml")
        self.before_run = self.workflow.data.get("before_run")
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.python = self._save_python_version("python")
        self.version = self.workflow.data.get("version")
        self.run_names = self.workflow.data["runs"]
        self.logdir = self.workflow.data.get("logdir")

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or "tensorboard"))
        if not workflow_name:
            parser.add_argument("run_names", metavar="RUN", type=str, nargs="+", help="A name of a run")
            parser.add_argument("--logdir", type=str, help="The path where TensorBoard will look for "
                                                           "event files. By default, TensorBoard will"
                                                           "scan all run artifacts.")
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args = parser.parse_args(self.provider_args)
        if self.run_as_provider:
            self.workflow.data["runs"] = args.run_names
            if args.logdir:
                self.workflow.data["logdir"] = args.logdir

    def create_jobs(self) -> List[Job]:
        return [Job(
            image="python:3.10",
            commands=self._commands(),
            port_count=1,
            apps=[App(
                port_index=0,
                app_name="tensorboard",
            )]
        )]

    def __get_jobs(self, run_names: List[str]):
        profile = self._profile()
        jobs_by_run = {}
        for run_name in run_names:
            jobs = get_jobs(run_name, profile)
            jobs_by_run[run_name] = jobs
        return jobs_by_run

    def _commands(self):
        commands = [
            "pip install boto3",
            "pip install tensorboard" + (f"=={self.version}" if self.version else ""),
        ]
        if self.before_run:
            commands.extend(self.before_run)

        logdir = []
        jobs_by_runs = self.__get_jobs(self.run_names)

        user_name = os.environ["DSTACK_USER"]

        dstack_aws_access_key_id = os.environ["DSTACK_AWS_ACCESS_KEY_ID"]
        dstack_aws_secret_access_key = os.environ["DSTACK_AWS_SECRET_ACCESS_KEY"]
        dstack_aws_default_region = os.environ["DSTACK_AWS_DEFAULT_REGION"]
        dstack_artifacts_s3_bucket = os.environ["DSTACK_ARTIFACTS_S3_BUCKET"]

        # TODO: Use user credentials and the user's or the job's artifact bucket if set

        # user_aws_access_key_id = os.environ["USER_AWS_ACCESS_KEY_ID"]
        # user_aws_secret_access_key = os.environ["USER_AWS_SECRET_ACCESS_KEY"]
        # user_aws_default_region = os.environ["USER_AWS_DEFAULT_REGION"]
        # user_artifacts_s3_bucket = os.environ["USER_ARTIFACTS_S3_BUCKET"]

        for run_name in jobs_by_runs:
            jobs = jobs_by_runs[run_name]
            for job in jobs:
                ld = f"s3://{dstack_artifacts_s3_bucket}/{user_name}/{run_name}/{job['job_id']}"
                if self.logdir:
                    ld += "/" + self.logdir
                logdir.append(ld)

        commands.append(f"AWS_ACCESS_KEY_ID={dstack_aws_access_key_id} "
                        f"AWS_SECRET_ACCESS_KEY={dstack_aws_secret_access_key} "
                        f"AWS_DEFAULT_REGION={dstack_aws_default_region} "
                        f"tensorboard --port $JOB_PORT_0 --host $JOB_HOSTNAME --logdir {','.join(logdir)}")
        return commands


def __provider__():
    return TensorboardProvider()


if __name__ == '__main__':
    __provider__().run()
