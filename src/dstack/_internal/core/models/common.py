from pydantic import BaseModel, Extra


class ForbidExtra(BaseModel):
    class Config:
        extra = Extra.forbid
