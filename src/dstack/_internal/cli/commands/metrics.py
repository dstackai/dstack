import argparse
import time
from typing import Optional

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
            help="Show only this replica. By default, all jobs are shown.",
            type=int,
        )
        self._parser.add_argument(
            "--job",
            help="Show only this job number. By default, all jobs are shown.",
            type=int,
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        jobs, metrics = self._fetch(args)

        if not args.watch:
            console.print(get_metrics_table(jobs, metrics))
            return

        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(get_metrics_table(jobs, metrics))
                    time.sleep(WATCH_INTERVAL_SECONDS)
                    jobs, metrics = self._fetch(args)
        except KeyboardInterrupt:
            pass

    def _fetch(self, args: argparse.Namespace) -> tuple[list[Job], list[JobMetrics]]:
        run = self.api.runs.get(run_name=args.run_name)
        if run is None:
            raise CLIError(f"Run {args.run_name} not found")
        jobs = select_jobs(run._run.jobs, args.replica, args.job)
        if not jobs:
            wanted = " ".join(
                f"{name}={value}"
                for name, value in (("replica", args.replica), ("job", args.job))
                if value is not None
            )
            raise CLIError(f"Run {args.run_name} has no job matching {wanted}")
        return jobs, [_get_job_metrics(self.api, run, job) for job in jobs]


def _get_job_metrics(api: Client, run: Run, job: Job) -> JobMetrics:
    """`limit` must be sent explicitly: the endpoint declares it `limit: int = 1`, not
    Optional, so omitting it caps the response at one sample."""
    return api.client.metrics.get_job_metrics(
        project_name=api.project,
        run_name=run.name,
        replica_num=job.job_spec.replica_num,
        job_num=job.job_spec.job_num,
        limit=MAX_SAMPLES,
    )


def select_jobs(jobs: list[Job], replica: Optional[int], job_num: Optional[int]) -> list[Job]:
    return [
        job
        for job in jobs
        if (replica is None or job.job_spec.replica_num == replica)
        and (job_num is None or job.job_spec.job_num == job_num)
    ]
