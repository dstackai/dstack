from typing import Any, List, Union

from dstack._internal.server.models import JobModel, RunModel


def fmt(model: Union[RunModel, JobModel]) -> str:
    """Consistent string representation of a model for logging."""
    if isinstance(model, RunModel):
        return f"run({model.id.hex[:6]}){model.run_name}"
    if isinstance(model, JobModel):
        return f"job({model.id.hex[:6]}){model.job_name}"
    return str(model)


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
