from os import PathLike
from pathlib import Path
from typing import Dict, Optional, Type, TypeVar

import yaml
from pydantic import BaseModel

from dstack.core.error import NotInitializedError
from dstack.core.userconfig import RepoUserConfig

Model = TypeVar("Model", bound=BaseModel)


class ConfigManager:
    def __init__(self, home: PathLike = "~/.dstack"):
        self.home = Path(home).expanduser().resolve()
        self._cache: Dict[str, BaseModel] = {}

    @property
    def repos(self) -> Path:
        return self.home / "repos"

    def repo_user_config_path(self, repo_dir: Optional[PathLike] = None) -> Path:
        """
        :param repo_dir: target repo directory path (default is cwd)
        :returns: a path to a local repo config
        """
        repo_dir = Path.cwd() if repo_dir is None else Path(repo_dir).resolve()
        return self.repos / f"{'.'.join(repo_dir.parts[1:])}.yaml"

    @property
    def repo_user_config(self) -> RepoUserConfig:
        try:
            return self._cached_read(self.repo_user_config_path(), RepoUserConfig)
        except FileNotFoundError:
            raise NotInitializedError("No repo user config found")

    def save_repo_user_config(self, value: RepoUserConfig):
        self._cached_write(self.repo_user_config_path(), value, mkdir=True)

    @staticmethod
    def write(path: PathLike, model: BaseModel, *, mkdir: bool = False, **kwargs):
        path = Path(path)
        if mkdir:
            path.parent.mkdir(exist_ok=True, parents=True)
        with path.open("w") as f:
            yaml.dump(model.dict(**kwargs), f)

    @staticmethod
    def read(path: PathLike, model: Type[Model], *, non_empty: bool = True) -> Model:
        try:
            with open(path, "r") as f:
                return model(**yaml.load(f, yaml.SafeLoader))
        except FileNotFoundError:
            if non_empty:
                raise
        return model()

    def _cached_read(self, path: PathLike, model: Type[Model], *, non_empty: bool = True) -> Model:
        key = str(Path(path).resolve())
        if key not in self._cache:
            self._cache[key] = self.read(path, model, non_empty=non_empty)
        return self._cache[key]

    def _cached_write(self, path: PathLike, model: BaseModel, *, mkdir: bool = False, **kwargs):
        key = str(Path(path).resolve())
        self._cache[key] = model
        self.write(path, model, mkdir=mkdir, **kwargs)


config = ConfigManager()
