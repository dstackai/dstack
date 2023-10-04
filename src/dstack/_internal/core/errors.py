import enum
from typing import List, Optional


class DstackError(Exception):
    pass


class ServerError(DstackError):
    pass


class ForbiddenError(ServerError):
    pass


class NotFoundError(ServerError):
    pass


class ClientError(DstackError):
    pass


class ServerClientErrorCode(str, enum.Enum):
    UNSPECIFIED_ERROR = "error"
    RESOURCE_EXISTS = "resource_exists"
    INVALID_CREDENTIALS = "invalid_credentials"
    BACKEND_NOT_AVAILABLE = "backend_not_available"
    REPO_DOES_NOT_EXIST = "repo_does_not_exist"


class ServerClientError(ServerError, ClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.UNSPECIFIED_ERROR
    msg: str = ""
    fields: List[List[str]] = []

    def __init__(self, msg: Optional[str] = None, fields: List[List[str]] = None):
        if msg is not None:
            self.msg = msg
        if fields is not None:
            self.fields = fields


class ResourceExistsError(ServerClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.RESOURCE_EXISTS
    msg = "Resource exists"


class BackendInvalidCredentialsError(ServerClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.INVALID_CREDENTIALS
    msg = "Invalid credentials"


class BackendNotAvailable(ServerClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.BACKEND_NOT_AVAILABLE
    msg = "Backend not available"


class RepoDoesNotExistError(ServerClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.REPO_DOES_NOT_EXIST

    @staticmethod
    def with_id(repo_id: str) -> "RepoDoesNotExistError":
        return RepoDoesNotExistError(f"Repo {repo_id} does not exist")


class BackendError(DstackError):
    pass


class BackendAuthError(BackendError):
    pass


class ComputeError(BackendError):
    pass


class NoCapacityError(ComputeError):
    pass


class ResourceNotFoundError(ComputeError):
    pass


class CLIError(DstackError):
    pass


class ConfigurationError(DstackError):
    pass


class SSHError(DstackError):
    pass
