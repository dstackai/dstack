from typing import Optional

from pydantic import BaseModel


class DeletePoolRequest(BaseModel):
    name: str
    force: bool


class CreatePoolRequest(BaseModel):
    name: str


class ShowPoolRequest(BaseModel):
    name: Optional[str]


class RemoveInstanceRequest(BaseModel):
    pool_name: str
    instance_name: str
    force: bool = False


class SetDefaultPoolRequest(BaseModel):
    pool_name: str
