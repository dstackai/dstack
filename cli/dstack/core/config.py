from abc import ABC
from pathlib import Path

import yaml


def get_config_path():
    return Path.joinpath(Path.home(), ".dstack", "config.yaml")


class BackendConfig(ABC):
    NAME = ""

    _configured = False

    @property
    def name(self):
        return self.NAME or ''

    def save(self, path: Path = get_config_path()):
        pass

    def load(self, path: Path = get_config_path()):
        pass

    def configure(self):
        ...

    @property
    def configured(self):
        return self._configured


"""
def load_config(path: Path = get_config_path()) -> BackendConfig:
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
    backend_type = DEFAULT_BACKEND
    if path.exists():
        with path.open() as f:
            config_data = yaml.load(f, Loader=yaml.FullLoader)
            backend_type = config_data.get("backend")
            if not backend_type:
                raise ConfigError(f"{path.resolve()} no backend is configured in {path.resolve()}")
    backend = LIST_CONFIG_BACKEND.get(backend_type)
    if not backend:
        raise Exception(f"Unsupported backend: {backend_type}")
    backend.load(path)
    return backend
"""
