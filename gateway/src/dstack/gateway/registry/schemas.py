from typing import Literal, Optional

from pydantic import BaseModel


class RegisterServiceRequest(BaseModel):
    run_id: str
    domain: str
    https: bool = True
    auth: bool = True
    options: dict = {}
    ssh_private_key: str


class RegisterReplicaRequest(BaseModel):
    job_id: str
    app_port: int
    ssh_host: str
    ssh_port: int
    ssh_jump_host: Optional[str] = None
    ssh_jump_port: Optional[int] = None


class RegisterEntrypointRequest(BaseModel):
    module: Literal["openai"]
    domain: str
    https: bool = True
