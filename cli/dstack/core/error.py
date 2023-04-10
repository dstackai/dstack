import os
import sys
from typing import List, Optional

from git import InvalidGitRepositoryError


class ConfigError(Exception):
    def __init__(self, message: Optional[str] = None):
        self.message = message


class HubConfigError(ConfigError):
    def __init__(self, message: str = "", code: str = "invalid_config", fields: List[str] = None):
        self.message = message
        self.code = code
        self.fields = fields if fields is not None else []


class BackendError(Exception):
    def __init__(self, message: Optional[str] = None):
        self.message = message


class SecretError(Exception):
    def __init__(self, message: Optional[str] = None):
        self.message = message


def check_config(func):
    def decorator(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except ConfigError:
            sys.exit(f"Call 'dstack config' first")

    return decorator


def check_git(func):
    def decorator(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except InvalidGitRepositoryError:
            sys.exit(f"{os.getcwd()} is not a Git repo")

    return decorator


def check_backend(func):
    def decorator(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except BackendError as e:
            sys.exit(e.message)

    return decorator
