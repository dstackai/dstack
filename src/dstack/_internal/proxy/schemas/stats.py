from pydantic import BaseModel


class Stat(BaseModel):
    requests: int
    request_time: float
