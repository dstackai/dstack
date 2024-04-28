from typing import TypedDict


class ServiceAccount(TypedDict):
    id: str
    service_account_id: str
    created_at: str
    key_algorithm: str
    public_key: str
    private_key: str


class ResourcesSpec(TypedDict):
    memory: int
    cores: int
    coreFraction: int
    gpus: int


class NebiusError(Exception):
    pass


class ClientError(NebiusError):
    pass


class ForbiddenError(NebiusError):
    pass


class NotFoundError(NebiusError):
    pass


class ConflictError(NebiusError):
    pass
