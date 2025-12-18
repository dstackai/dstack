import uuid
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
        return fmt_entity("run", model.id, model.run_name)
    if isinstance(model, JobModel):
        return fmt_entity("job", model.id, model.job_name)
    if isinstance(model, InstanceModel):
        return fmt_entity("instance", model.id, model.name)
    if isinstance(model, GatewayModel):
        return fmt_entity("gateway", model.id, model.name)
    if isinstance(model, ProbeModel):
        return fmt_entity("probe", model.id, model.name)
    return str(model)


def fmt_entity(entity_type: str, entity_id: uuid.UUID, entity_name: str) -> str:
    return f"{entity_type}({entity_id.hex[:6]}){entity_name}"
