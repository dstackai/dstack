import time
from typing import Iterable, Optional

from dstack._internal.core.models.runs import Run
from dstack.api.server import APIClient


def poll_run(
    api_client: APIClient,
    project_name: str,
    run_name: str,
    delay: float = 5.0,
    timeout: Optional[float] = None,
) -> Iterable[Run]:
    """
    Polls run every `delay` seconds until `timeout` is reached (if any).
    :param api_client: Dstack server APIClient
    :param project_name: Project name
    :param run_name: Run name
    :param delay: How often to poll run, default is 5 seconds
    :param timeout: Timeout in seconds, default is None (no timeout)
    :yield: Run model
    """
    start_time = time.monotonic()
    while True:
        run = api_client.runs.get(project_name, run_name)
        yield run
        now = time.monotonic()
        sleep = delay
        if timeout is not None:
            if now > start_time + timeout:
                raise TimeoutError()
            sleep = min(sleep, start_time + timeout - now)
        time.sleep(sleep)
