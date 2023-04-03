from pydantic import BaseModel, validator


class CacheSpec(BaseModel):
    path: str

    @validator("path")
    def remove_rel_prefix(cls, v: str) -> str:
        rel_prefix = "./"
        while v.startswith(rel_prefix):
            v = v[len(rel_prefix) :]
        return v
