from os import PathLike
from pathlib import Path
from typing import Type, TypeVar

import yaml
from pydantic import BaseModel

Model = TypeVar("Model", bound=BaseModel)


class BaseConfig:
    def __init__(self, home: PathLike = "~/.dstack"):
        self.home = Path(home).expanduser().resolve()

    @property
    def repos(self) -> Path:
        return self.home / "repos"

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
