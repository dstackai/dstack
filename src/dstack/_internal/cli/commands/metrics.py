import argparse
import time

from rich.live import Live

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import RunNameCompleter
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    console,
)
from dstack._internal.cli.utils.metrics import (
    MAX_SAMPLES,
    WATCH_INTERVAL_SECONDS,
    get_metrics_table,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.metrics import JobMetrics
from dstack._internal.core.models.runs import Job
from dstack.api._public import Client
from dstack.api._public.runs import Run


class MetricsCommand(APIBaseCommand):
    NAME = "metrics"
    DESCRIPTION = "Show run metrics"

    def _register(self):
        super()._register()
        self._parser.add_argument("run_name").completer = RunNameCompleter()  # type: ignore[attr-defined]
        self._parser.add_argument(
            "-w",
            "--watch",
            help="Watch run metrics in realtime",
            action="store_true",
        )
        self._parser.add_argument(
            "--replica",
            help="The replica number. Defaults to 0.",
            type=int,
            default=0,
        )
        self._parser.add_argument(
            "--job",
            help="The job number inside the replica. Defaults to 0.",
            type=int,
            default=0,
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        job, metrics = self._fetch(args)

        if not args.watch:
            console.print(get_metrics_table(job, metrics))
            return

        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(get_metrics_table(job, metrics))
                    time.sleep(WATCH_INTERVAL_SECONDS)
                    job, metrics = self._fetch(args)
        except KeyboardInterrupt:
            pass

    def _fetch(self, args: argparse.Namespace) -> tuple[Job, JobMetrics]:
        run = self.api.runs.get(run_name=args.run_name)
        if run is None:
            raise CLIError(f"Run {args.run_name} not found")
        job = _get_job(run, args.replica, args.job)
        return job, _get_job_metrics(self.api, run, job)


def _get_job(run: Run, replica_num: int, job_num: int) -> Job:
    for job in run._run.jobs:
        if job.job_spec.replica_num == replica_num and job.job_spec.job_num == job_num:
            return job
    raise CLIError(
        f"Run {run.name} has no replica={replica_num} job={job_num}."
        " Use --replica and --job to select one."
    )


def _get_job_metrics(api: Client, run: Run, job: Job) -> JobMetrics:
    """Ask for everything retained, as the UI does.

    `limit` must be sent explicitly: the endpoint declares it as `limit: int = 1`, not
    Optional, so omitting it caps the response at a single sample.
    """
    return api.client.metrics.get_job_metrics(
        project_name=api.project,
        run_name=run.name,
        replica_num=job.job_spec.replica_num,
        job_num=job.job_spec.job_num,
        limit=MAX_SAMPLES,
    )
