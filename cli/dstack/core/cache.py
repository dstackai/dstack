from pydantic import BaseModel


class CacheSpec(BaseModel):
    path: str
