from typing import List, Optional


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
