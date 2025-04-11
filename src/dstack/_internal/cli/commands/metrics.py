import argparse
import time
from typing import Any, Dict, List, Optional, Union

from rich.live import Live
from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import RunNameCompleter
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    add_row_from_dict,
    console,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.instances import Resources
from dstack._internal.core.models.metrics import JobMetrics
from dstack.api._public import Client
from dstack.api._public.runs import Run


class MetricsCommand(APIBaseCommand):
    NAME = "metrics"
    DESCRIPTION = "Show run metrics"

    def _register(self):
        super()._register()
        self._parser.add_argument("run_name").completer = RunNameCompleter()
        self._parser.add_argument(
            "-w",
            "--watch",
            help="Watch run metrics in realtime",
            action="store_true",
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        run = self.api.runs.get(run_name=args.run_name)
        if run is None:
            raise CLIError(f"Run {args.run_name} not found")
        if run.status.is_finished():
            raise CLIError(f"Run {args.run_name} is finished")
        metrics = _get_run_jobs_metrics(api=self.api, run=run)

        if not args.watch:
            console.print(_get_metrics_table(run, metrics))
            return

        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(_get_metrics_table(run, metrics))
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    run = self.api.runs.get(run_name=args.run_name)
                    if run is None:
                        raise CLIError(f"Run {args.run_name} not found")
                    if run.status.is_finished():
                        raise CLIError(f"Run {args.run_name} is finished")
                    metrics = _get_run_jobs_metrics(api=self.api, run=run)
        except KeyboardInterrupt:
            pass


def _get_run_jobs_metrics(api: Client, run: Run) -> List[JobMetrics]:
    metrics = []
    for job in run._run.jobs:
        job_metrics = api.client.metrics.get_job_metrics(
            project_name=api.project,
            run_name=run.name,
            replica_num=job.job_spec.replica_num,
            job_num=job.job_spec.job_num,
        )
        metrics.append(job_metrics)
    return metrics


def _get_metrics_table(run: Run, metrics: List[JobMetrics]) -> Table:
    table = Table(box=None)
    table.add_column("NAME", style="bold", no_wrap=True)
    table.add_column("CPU")
    table.add_column("MEMORY")
    table.add_column("GPU")

    run_row: Dict[Union[str, int], Any] = {"NAME": run.name}
    if len(run._run.jobs) != 1:
        add_row_from_dict(table, run_row)

    for job, job_metrics in zip(run._run.jobs, metrics):
        jrd = job.job_submissions[-1].job_runtime_data
        jpd = job.job_submissions[-1].job_provisioning_data
        resources: Optional[Resources] = None
        if jrd is not None and jrd.offer is not None:
            resources = jrd.offer.instance.resources
        elif jpd is not None:
            resources = jpd.instance_type.resources
        cpu_usage = _get_metric_value(job_metrics, "cpu_usage_percent")
        if cpu_usage is not None:
            if resources is not None:
                cpu_usage = cpu_usage / resources.cpus
            cpu_usage = f"{cpu_usage:.0f}%"
        memory_usage = _get_metric_value(job_metrics, "memory_working_set_bytes")
        if memory_usage is not None:
            memory_usage = f"{round(memory_usage / 1024 / 1024)}MB"
            if resources is not None:
                memory_usage += f"/{resources.memory_mib}MB"
        gpu_metrics = ""
        gpus_detected_num = _get_metric_value(job_metrics, "gpus_detected_num")
        if gpus_detected_num is not None:
            for i in range(gpus_detected_num):
                gpu_memory_usage = _get_metric_value(job_metrics, f"gpu_memory_usage_bytes_gpu{i}")
                gpu_util_percent = _get_metric_value(job_metrics, f"gpu_util_percent_gpu{i}")
                if gpu_memory_usage is not None:
                    if i != 0:
                        gpu_metrics += "\n"
                    gpu_metrics += f"#{i} {round(gpu_memory_usage / 1024 / 1024)}MB"
                    if resources is not None:
                        gpu_metrics += f"/{resources.gpus[i].memory_mib}MB"
                    gpu_metrics += f" {gpu_util_percent}% Util"

        job_row: Dict[Union[str, int], Any] = {
            "NAME": f"  replica={job.job_spec.replica_num} job={job.job_spec.job_num}",
            "CPU": cpu_usage or "-",
            "MEMORY": memory_usage or "-",
            "GPU": gpu_metrics or "-",
        }
        if len(run._run.jobs) == 1:
            job_row.update(run_row)
        add_row_from_dict(table, job_row)

    return table


def _get_metric_value(job_metrics: JobMetrics, name: str) -> Optional[Any]:
    for metric in job_metrics.metrics:
        if metric.name == name:
            return metric.values[-1]
    return None
