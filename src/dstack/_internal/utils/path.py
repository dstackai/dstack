import os
from pathlib import Path
from typing import Union

PathLike = Union[str, os.PathLike]


def path_in_dir(path: PathLike, directory: PathLike) -> bool:
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
        return True
    except ValueError:
        return False
