from pydantic import BaseModel

import dstack.gateway.schemas
import dstack.gateway.services.store as store


class RegisterRequest(dstack.gateway.schemas.Service):
    pass  # TODO(egor-s): adapters and auth requirements


class UnregisterRequest(BaseModel):
    public_domain: str
