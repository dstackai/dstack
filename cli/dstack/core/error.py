from typing import Optional


class DstackError(Exception):
    def __init__(self, message: Optional[str] = None):
        self.message = message


class BackendError(DstackError):
    def __init__(self, message: Optional[str] = None):
        self.message = message


class NoMatchingInstanceError(BackendError):
    code = "no_matching_instance"


class RepoNotInitializedError(DstackError):
    pass


class NameNotFoundError(DstackError):
    pass
