from pydantic import BaseModel


class DepSpec(BaseModel):
    repo_id: str
    run_name: str
    mount: bool
