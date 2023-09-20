import enum
from typing import List, Optional


class DstackError(Exception):
    pass


class ServerError(DstackError):
    pass


class ForbiddenError(ServerError):
    pass


class ClientError(DstackError):
    pass


class ServerClientErrorCode(str, enum.Enum):
    UNSPECIFIED_ERROR = "error"
    INVALID_CREDENTIALS = "invalid_credentials"
    BACKEND_NOT_AVAILABLE = "backend_not_available"


class ServerClientError(ServerError, ClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.UNSPECIFIED_ERROR
    msg: str = ""
    fields: List[List[str]] = []

    def __init__(self, msg: Optional[str] = None, fields: List[List[str]] = None):
        if msg is not None:
            self.msg = msg
        if fields is not None:
            self.fields = fields


class BackendInvalidCredentialsError(ServerClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.INVALID_CREDENTIALS
    msg = "Invalid credentials"


class BackendNotAvailable(ServerClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.BACKEND_NOT_AVAILABLE
    msg = "Backend not available"


class BackendError(DstackError):
    pass


class ComputeError(BackendError):
    pass


class NoCapacityError(ComputeError):
    pass


class ResourceNotFoundError(ComputeError):
    pass
