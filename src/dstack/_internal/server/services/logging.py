from typing import Union

from dstack._internal.server.models import JobModel, RunModel


def fmt(model: Union[RunModel, JobModel]) -> str:
    """Consistent string representation of a model for logging."""
    if isinstance(model, RunModel):
        return f"run({model.id.hex[:6]}){model.run_name}"
    if isinstance(model, JobModel):
        return f"job({model.id.hex[:6]}){model.job_name}"
    return str(model)
