from abc import ABC
from pathlib import Path
from typing import Optional

import yaml


class BackendConfig(ABC):
    def __init__(self):
        pass


class AwsBackendConfig(BackendConfig):
    def __init__(self, bucket_name: str, region_name: Optional[str], profile_name: Optional[str]):
        super().__init__()
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.profile_name = profile_name


class Config:
    def __init__(self, backend: BackendConfig):
        self.backend = backend


def get_config_path():
    return Path.home() / ".dstack" / "config.yaml"


class ConfigError(Exception):
    def __init__(self, message: str):
        self.message = message


def load_config(path: Path = get_config_path()) -> Config:
    if path.exists():
        with path.open() as f:
            config_data = yaml.load(f, Loader=yaml.FullLoader)
            backend_name = config_data.get("backend")
            if not backend_name:
                raise ConfigError(f"{path.resolve()} no backend is configured in {path.resolve()}")
            elif backend_name != "aws":
                raise ConfigError(f"Unknown backend: {backend_name}")
            else:
                return Config(AwsBackendConfig(config_data["bucket"],
                                               config_data.get("region"),
                                               config_data.get("profile")))
    else:
        raise ConfigError(f"{path.resolve()} doesn't exist")


def save_config(config: Config, path: Path = get_config_path()):
    if isinstance(config.backend, AwsBackendConfig):
        with path.open('w') as f:
            config_data = {
                "backend": "aws",
                "bucket": config.backend.bucket_name
            }
            if config.backend.region_name:
                config_data["region"] = config.backend.region_name
            if config.backend.profile_name:
                config_data["profile"] = config.backend.profile_name
            yaml.dump(config_data, f)
    else:
        raise Exception(f"Unsupported backend: {config.backend}")

