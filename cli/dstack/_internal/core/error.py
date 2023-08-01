from typing import List, Optional


class DstackError(Exception):
    def __init__(self, message: Optional[str] = None):
        self.message = message


class BackendError(DstackError):
    pass


class BackendValueError(BackendError):
    code = "backend_value_error"


class BackendAuthError(BackendError):
    code = "invalid_backend_credentials"


class BackendNotAvailableError(BackendError):
    code = "backend_not_available"


class NoMatchingInstanceError(BackendError):
    code = "no_matching_instance"


class RepoNotInitializedError(DstackError):
    def __init__(self, message: Optional[str] = None, project_name: Optional[str] = None):
        super().__init__(message)
        self.project_name = project_name


class NameNotFoundError(DstackError):
    pass


class SSHCommandError(BackendError):
    code = "ssh_command_error"

    def __init__(self, cmd: List[str], message: str):
        super().__init__(message)
        self.cmd = cmd
