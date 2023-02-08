from pathlib import Path

import yaml

from dstack.core.config import BackendConfig, get_config_path, get_dstack_dir


class LocalConfig(BackendConfig):
    def __init__(self):
        super().__init__()
        self.path = get_dstack_dir()

    def load(self, path: Path = get_config_path()):
        super().load(path=path)
        if path.exists():
            with path.open() as f:
                config_data = yaml.load(f, Loader=yaml.FullLoader)
                self.path = config_data.get("path") or get_dstack_dir()

    def save(self, path: Path = get_config_path()):
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        with path.open("w") as f:
            config_data = {"backend": "local", "path": self.path}
            yaml.dump(config_data, f)
