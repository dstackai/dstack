from pathlib import Path

from dstack._internal.utils.path import PathLike


def find_configuration_file(
    base_dir: PathLike, working_dir: PathLike, configuration_file: PathLike
) -> Path:
    base_dir = Path(base_dir)
    working_dir = working_dir or "."
    if configuration_file:
        return (base_dir / configuration_file).absolute()
    configuration_path = base_dir / working_dir / ".dstack.yaml"
    if configuration_path.exists():
        return configuration_path
    return configuration_path.with_suffix(".yml")
