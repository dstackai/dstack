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


class URLNotFoundError(ClientError):
    pass


class MethodNotAllowedError(ClientError):
    pass


class ServerClientErrorCode(str, enum.Enum):
    UNSPECIFIED_ERROR = "error"
    RESOURCE_EXISTS = "resource_exists"
    RESOURCE_NOT_EXISTS = "resource_not_exists"
    INVALID_CREDENTIALS = "invalid_credentials"
    BACKEND_NOT_AVAILABLE = "backend_not_available"
    REPO_DOES_NOT_EXIST = "repo_does_not_exist"
    GATEWAY_ERROR = "gateway_error"


class ServerClientError(ServerError, ClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.UNSPECIFIED_ERROR
    msg: str = ""
    fields: List[List[str]] = []

    def __init__(self, msg: Optional[str] = None, fields: Optional[List[List[str]]] = None):
        if msg is not None:
            self.msg = msg
        super().__init__(self.msg)  # show the message in stacktrace
        if fields is not None:
            self.fields = fields


class ResourceExistsError(ServerClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.RESOURCE_EXISTS
    msg = "Resource exists"


class ResourceNotExistsError(ServerClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.RESOURCE_NOT_EXISTS
    msg = "Resource not found"


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


class GatewayError(ServerClientError):
    code: ServerClientErrorCode = ServerClientErrorCode.GATEWAY_ERROR
    msg = "Gateway error"


class BackendError(DstackError):
    pass


class BackendAuthError(BackendError):
    pass


class ComputeError(BackendError):
    pass


class NoCapacityError(ComputeError):
    pass


class ProvisioningError(ComputeError):
    pass


class ComputeResourceNotFoundError(ComputeError):
    pass


class PlacementGroupInUseError(ComputeError):
    pass


class PlacementGroupNotSupportedError(ComputeError):
    pass


class NotYetTerminated(ComputeError):
    """
    Used by Compute.terminate_instance to signal that instance termination is not complete
    and the method should be called again after some time to continue termination.
    """

    def __init__(self, details: str) -> None:
        """
        Args:
            details: some details about the termination status
        """
        return super().__init__(details)


class CLIError(DstackError):
    pass


class ConfigurationError(DstackError):
    pass


class SSHProvisioningError(DstackError):
    pass


class SSHError(DstackError):
    pass


class SSHTimeoutError(SSHError):
    pass


class SSHConnectionRefusedError(SSHError):
    pass


class SSHKeyError(SSHError):
    pass


class SSHPortInUseError(SSHError):
    pass


class DockerRegistryError(DstackError):
    pass


class RepoError(DstackError):
    pass


class RepoDetachedHeadError(RepoError):
    pass


class RepoInvalidCredentialsError(RepoError):
    pass


class RepoGitError(RepoError):
    """
    A wrapper for `git.exc.GitError` and its subclasses.

    Should be raised with `from e` clause to indicate the underlying exception.
    To build a message from the underlying exception, raise this exception without arguments.

        try:
            ...
        except git.GitError as e:
            raise RepoGitError() from e
    """

    def __str__(self) -> str:
        if self.args or self.__cause__ is None:
            return super().__str__()
        return f"{self.__cause__.__class__.__name__}: {self.__cause__}"


class RepoInvalidGitRepositoryError(RepoGitError):
    """
    `DstackError` counterpart for `git.exc.InvalidGitRepositoryError`.
    """
