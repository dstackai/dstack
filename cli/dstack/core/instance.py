from pydantic import BaseModel

from dstack.core.runners import Resources


class InstanceType(BaseModel):
    instance_name: str
    resources: Resources

    def __str__(self) -> str:
        return f'InstanceType(instance_name="{self.instance_name}", resources={self.resources})'
