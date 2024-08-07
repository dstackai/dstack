from typing import Optional, Tuple

import dstack._internal.core.services.configs as configs
from dstack._internal.core.errors import ConfigurationError
from dstack.api.server import APIClient


def get_api_client(project_name: Optional[str] = None) -> Tuple[APIClient, str]:
    config = configs.ConfigManager()
    project = config.get_project_config(project_name)
    if project is None:
        if project_name is not None:
            raise ConfigurationError(f"Project {project_name} is not configured")
        raise ConfigurationError("No default project, specify project name")
    return APIClient(project.url, project.token), project.name
