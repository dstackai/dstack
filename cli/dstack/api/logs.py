import sys
from datetime import datetime

from dstack.backend.base import Backend


def poll_logs(
    backend: Backend,
    run_name: str,
    start_time: datetime,
):
    try:
        for event in backend.poll_logs(run_name=run_name, start_time=start_time):
            sys.stdout.write(event.log_message)
    except KeyboardInterrupt:
        pass
