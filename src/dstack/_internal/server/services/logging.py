from typing import Union

from dstack._internal.server.models import (
    GatewayModel,
    InstanceModel,
    JobModel,
    ProbeModel,
    RunModel,
)


def fmt(model: Union[RunModel, JobModel, InstanceModel, GatewayModel, ProbeModel]) -> str:
    """Consistent string representation of a model for logging."""
    if isinstance(model, RunModel):
        return f"run({model.id.hex[:6]}){model.run_name}"
    if isinstance(model, JobModel):
        return f"job({model.id.hex[:6]}){model.job_name}"
    if isinstance(model, InstanceModel):
        return f"instance({model.id.hex[:6]}){model.name}"
    if isinstance(model, GatewayModel):
        return f"gateway({model.id.hex[:6]}){model.name}"
    if isinstance(model, ProbeModel):
        return f"probe({model.id.hex[:6]}){model.name}"
    return str(model)
