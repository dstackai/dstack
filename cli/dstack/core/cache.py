from pydantic import BaseModel, validator


class CacheSpec(BaseModel):
    path: str
