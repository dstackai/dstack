from pydantic import BaseModel, validator


class CacheSpec(BaseModel):
    path: str

    @validator("path")
    def remove_dot_relative(cls, v: str) -> str:
        return v.lstrip("./")
