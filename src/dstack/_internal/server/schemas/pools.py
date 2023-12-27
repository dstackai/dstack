from pydantic import BaseModel


class DeletePoolRequest(BaseModel):
    name: str
    force: bool


class CreatePoolRequest(BaseModel):
    name: str


class ShowPoolRequest(BaseModel):
    name: str
