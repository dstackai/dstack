from pydantic import BaseModel


class DeletePoolRequest(BaseModel):  # type: ignore[misc,valid-type]
    name: str
    force: bool


class CreatePoolRequest(BaseModel):  # type: ignore[misc,valid-type]
    name: str


class ShowPoolRequest(BaseModel):  # type: ignore[misc,valid-type]
    name: str


class RemoveInstanceRequest(BaseModel):  # type: ignore[misc,valid-type]
    pool_name: str
    instance_name: str


class SetDefaultPoolRequest(BaseModel):  # type: ignore[misc,valid-type]
    pool_name: str
