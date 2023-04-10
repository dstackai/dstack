from pydantic import BaseModel


class DepSpec(BaseModel):
    repo_name: str
    run_name: str
    mount: bool
