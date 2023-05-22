import json
from datetime import datetime
from typing import Dict, Generator, Optional

from file_read_backwards import FileReadBackwards

from dstack.backend.base.logs import render_log_message
from dstack.backend.base.storage import Storage
from dstack.backend.local.config import LocalConfig
from dstack.core.log_event import LogEvent

LOGS_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


def poll_logs(
    backend_config: LocalConfig,
    storage: Storage,
    repo_id: str,
    run_name: str,
    start_time: datetime,
    end_time: Optional[datetime],
    descending: bool,
) -> Generator[LogEvent, None, None]:
    jobs_cache = {}
    logs_filepath = (
        backend_config.backend_dir / "logs" / "dstack" / "jobs" / repo_id / f"{run_name}.log"
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
                yield render_log_message(storage, event, repo_id, jobs_cache)
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
