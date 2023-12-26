from typing import Optional

from pydantic import BaseModel

import dstack.gateway.schemas


class RegisterRequest(dstack.gateway.schemas.Service):
    pass  # TODO(egor-s): adapters and auth requirements


class UnregisterRequest(BaseModel):
    public_domain: str


class RegisterEntrypointRequest(BaseModel):
    domain: str


class PreflightRequest(BaseModel):
    public_domain: str
    ssh_private_key: str

    options: dict = {}
