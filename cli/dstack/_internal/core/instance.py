from pydantic import BaseModel

from dstack._internal.core.runners import Resources


class InstanceType(BaseModel):
    instance_name: str
    resources: Resources
