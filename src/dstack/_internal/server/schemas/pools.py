from typing import Optional

from dstack._internal.core.models.common import CoreModel


class DeletePoolRequest(CoreModel):
    name: str
    force: bool


class CreatePoolRequest(CoreModel):
    name: str


class ShowPoolRequest(CoreModel):
    name: Optional[str]


class RemoveInstanceRequest(CoreModel):
    pool_name: str
    instance_name: str
    force: bool = False


class SetDefaultPoolRequest(CoreModel):
    pool_name: str
