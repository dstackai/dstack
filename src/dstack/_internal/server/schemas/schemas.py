from pydantic import BaseModel


class GetUserRequest(BaseModel):
    username: str
