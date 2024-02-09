from typing import Optional

from pydantic import BaseModel


class DeletePoolRequest(BaseModel):  # type: ignore[misc]
    name: str
    force: bool


class CreatePoolRequest(BaseModel):  # type: ignore[misc]
    name: str


class ShowPoolRequest(BaseModel):  # type: ignore[misc]
    name: Optional[str]


class RemoveInstanceRequest(BaseModel):  # type: ignore[misc]
    pool_name: str
    instance_name: str
    force: bool = False


class SetDefaultPoolRequest(BaseModel):  # type: ignore[misc]
    pool_name: str
