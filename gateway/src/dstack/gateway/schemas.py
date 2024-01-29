from typing import Optional

from pydantic import BaseModel


class Service(BaseModel):
    public_domain: str  # only https & 443 port
    app_port: int
    ssh_host: str  # user@hostname
    ssh_port: int
    docker_ssh_host: Optional[str] = None
    docker_ssh_port: Optional[int] = None

    auth: bool = True
    options: dict = {}
