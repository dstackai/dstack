from pathlib import Path
from typing import Optional, Tuple

import yaml

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import AnyRunConfiguration, parse
from dstack._internal.utils.path import PathLike, path_in_dir


def load_configuration(
    repo_dir: PathLike, working_dir: PathLike, configuration_file: Optional[PathLike]
) -> Tuple[AnyRunConfiguration, str]:
    """
    :return: configuration, relative path to the configuration file
    """
    repo_dir = Path(repo_dir)

    if configuration_file is None:
        configuration_file = repo_dir / working_dir / ".dstack.yml"
        if not configuration_file.exists():
            configuration_file = configuration_file.with_suffix(".yaml")
    else:
        configuration_file = Path(configuration_file)
    if not path_in_dir(configuration_file, repo_dir):
        raise ConfigurationError(
            f"Configuration file {configuration_file} is not in the repository {repo_dir}"
        )

    try:
        with configuration_file.open("r") as f:
            return parse(yaml.safe_load(f)), str(configuration_file.relative_to(repo_dir))
    except FileNotFoundError:
        raise ConfigurationError(f"Configuration file {configuration_file} does not exist")
