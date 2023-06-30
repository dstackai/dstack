import json
from datetime import datetime
from typing import Dict, Generator, Optional

from file_read_backwards import FileReadBackwards

from dstack._internal.backend.base import jobs as base_jobs
from dstack._internal.backend.base.logs import Logging, fix_log_event_urls, render_log_event
from dstack._internal.backend.base.storage import Storage
from dstack._internal.backend.local.config import LocalConfig
from dstack._internal.core.log_event import LogEvent

LOGS_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


class LocalLogging(Logging):
    def __init__(self, backend_config: LocalConfig):
        self.backend_config = backend_config

    def poll_logs(
        self,
        storage: Storage,
        repo_id: str,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime],
        descending: bool,
        diagnose: bool,
    ) -> Generator[LogEvent, None, None]:
        jobs = base_jobs.list_jobs(storage, repo_id, run_name)
        jobs_map = {j.job_id: j for j in jobs}
        if diagnose:
            runner_id = jobs[0].runner_id
            logs_filepath = (
                self.backend_config.backend_dir
                / "logs"
                / "dstack"
                / "runners"
                / f"{runner_id}.log"
            )
        else:
            logs_filepath = (
                self.backend_config.backend_dir
                / "logs"
                / "dstack"
                / "jobs"
                / repo_id
                / f"{run_name}.log"
            )
        if descending:
            log_file = FileReadBackwards(logs_filepath)
        else:
            log_file = open(logs_filepath, "r")
        found_log = False
        with log_file as f:
            for line in f:
                event = _log_line_to_log_event(line)
                if start_time <= event["timestamp"] and (
                    end_time is None or event["timestamp"] <= end_time
                ):
                    found_log = True
                    log_event = render_log_event(event)
                    if not diagnose:
                        log_event = fix_log_event_urls(log_event, jobs_map)
                    yield log_event
                else:
                    if found_log:
                        break


def _log_line_to_log_event(line: str) -> Dict:
    log_line_dict = dict(record.split("=", maxsplit=1) for record in line.split(" ", maxsplit=2))
    log_line_dict = {k: v.strip().strip('"') for k, v in log_line_dict.items()}
    log_msg = json.loads(log_line_dict["msg"].encode().decode("unicode_escape"))
    return {
        "eventId": log_msg["event_id"],
        "timestamp": datetime.strptime(log_line_dict["time"], LOGS_TIME_FORMAT),
        "message": {
            "source": "stdout",
            "log": log_msg["log"],
            "job_id": log_msg["job_id"],
        },
    }
