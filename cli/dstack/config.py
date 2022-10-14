import os
from abc import ABC
from pathlib import Path
from typing import Optional

import yaml


class BackendConfig(ABC):
    def __init__(self):
        pass


class AwsBackendConfig(BackendConfig):
    def __init__(self, profile_name: Optional[str], region_name: Optional[str], bucket_name: str,
                 subnet_id: Optional[str]):
        super().__init__()
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.profile_name = profile_name
        self.subnet_id = subnet_id


class Config:
    def __init__(self, backend_config: BackendConfig):
        self.backend_config = backend_config


def get_config_path():
    return Path.home() / ".dstack" / "config.yaml"


class ConfigError(Exception):
    def __init__(self, message: str):
        self.message = message


def load_config(path: Path = get_config_path()) -> Config:
    bucket_name = os.getenv("DSTACK_AWS_S3_BUCKET")
    if bucket_name:
        return Config(AwsBackendConfig(os.getenv("DSTACK_AWS_PROFILE") or os.getenv("AWS_PROFILE"),
                                       os.getenv("DSTACK_AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"), bucket_name,
                                       os.getenv("DSTACK_AWS_EC2_SUBNET")))
    else:
        if path.exists():
            with path.open() as f:
                config_data = yaml.load(f, Loader=yaml.FullLoader)
                backend_name = config_data.get("backend")
                if not backend_name:
                    raise ConfigError(f"{path.resolve()} no backend is configured in {path.resolve()}")
                elif backend_name != "aws":
                    raise ConfigError(f"Unknown backend: {backend_name}")
                else:
                    return Config(AwsBackendConfig(config_data.get("profile") or os.getenv("AWS_PROFILE"),
                                                   config_data.get("region") or os.getenv("AWS_DEFAULT_REGION"),
                                                   config_data["bucket"],
                                                   config_data.get("subnet")))
        else:
            raise ConfigError(f"{path.resolve()} doesn't exist")


def write_config(config: Config, path: Path = get_config_path()):
    if isinstance(config.backend_config, AwsBackendConfig):
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        with path.open('w') as f:
            config_data = {
                "backend": "aws",
                "bucket": config.backend_config.bucket_name
            }
            if config.backend_config.region_name:
                config_data["region"] = config.backend_config.region_name
            if config.backend_config.profile_name:
                config_data["profile"] = config.backend_config.profile_name
            if config.backend_config.subnet_id:
                config_data["subnet"] = config.backend_config.subnet_id
            yaml.dump(config_data, f)
    else:
        raise Exception(f"Unsupported backend: {config.backend_config}")

