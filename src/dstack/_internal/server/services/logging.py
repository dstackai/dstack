from typing import Any, List

from dstack._internal.server.models import JobModel


def job_log(message: str, job_model: JobModel, *args: Any) -> List[Any]:
    """Build args for `logger.info` or similar.

    Args:
        message: c-style format string for `args`
        job_model: job to log
        *args: substituted into `message`

    Returns:
        final format string and args
    """
    # job_name is not unique across projects, so we add job_id prefix
    return [f"(%s)%s: {message}", job_model.id.hex[:6], job_model.job_name, *args]
