import os.path
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from pygtail import Pygtail

from dstack.backend.base import jobs, runs
from dstack.backend.base.compute import Compute
from dstack.backend.base.logs import render_log_message
from dstack.backend.base.storage import Storage
from dstack.core.job import JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import RepoAddress

WAIT_N_ONCE_FINISHED = 1

CHECK_STATUS_EVERY_N = 3

POLL_LOGS_RATE_SECS = 1


def events_loop(
    storage: Storage, compute: Compute, repo_address: RepoAddress, job_heads: List[JobHead]
):
    counter = 0
    finished_counter = 0
    tails = {}

    _jobs = [jobs.get_job(storage, repo_address, job_head.job_id) for job_head in job_heads]
    for _job in _jobs:
        path_dir = (
            Path.home()
            / ".dstack"
            / "tmp"
            / "runner"
            / "configs"
            / _job.runner_id
            / "logs"
            / "jobs"
            / repo_address.path()
        )  # TODO Hardcode
        file_log = f"{_job.run_name}.log"  # TODO Hardcode
        if not path_dir.exists():
            path_dir.mkdir(parents=True)
            f = open(path_dir / file_log, "w")
            f.close()
        tails[_job.job_id] = Pygtail(
            os.path.join(path_dir, file_log), save_on_end=False, copytruncate=False
        )

    while True:
        if counter % CHECK_STATUS_EVERY_N == 0:
            _jobs = [
                jobs.get_job(storage, repo_address, job_head.job_id) for job_head in job_heads
            ]

            for _job in _jobs:
                for line_log in tails[_job.job_id]:
                    yield {
                        "message": {
                            "source": "stdout",
                            "log": line_log.rstrip("\n"),
                            "job_id": _job.job_id,
                        },
                        "eventId": _job.runner_id,
                        "timestamp": time.time(),
                    }

            run = next(
                iter(runs.get_run_heads(storage, compute, _jobs, include_request_heads=False))
            )
            if run.status.is_finished():
                if finished_counter == WAIT_N_ONCE_FINISHED:
                    break
                finished_counter += 1
        counter = counter + 1
        time.sleep(POLL_LOGS_RATE_SECS)


def poll_logs(
    storage: Storage,
    compute: Compute,
    repo_address: RepoAddress,
    job_heads: List[JobHead],
    start_time: int,
    attached: bool,
) -> Generator[LogEvent, None, None]:
    jobs_cache = {}
    try:
        # Read log_file
        for event in events_loop(storage, compute, repo_address, job_heads):
            yield render_log_message(storage, event, repo_address, jobs_cache)
    except Exception as e:
        raise e
