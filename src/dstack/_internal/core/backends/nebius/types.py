from typing import List, Literal, Optional, TypedDict


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
    gpus: Literal[0, 1, 2, 4, 8]


class NebiusError(Exception):
    pass


class ForbiddenError(NebiusError):
    pass


class ConflictError(NebiusError):
    pass
