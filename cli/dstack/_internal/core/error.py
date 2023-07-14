from typing import Optional


class DstackError(Exception):
    def __init__(self, message: Optional[str] = None):
        self.message = message


class BackendError(DstackError):
    pass


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
