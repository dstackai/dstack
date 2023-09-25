from typing import Optional, Tuple

import dstack._internal.core.services.configs as configs
from dstack._internal.core.errors import DstackError
from dstack.api.server import APIClient


def get_api_client(project_name: Optional[str] = None) -> Tuple[APIClient, str]:
    config = configs.ConfigManager()
    project = config.get_project_config(project_name)
    if project is None:
        if project_name is not None:
            raise DstackError(f"Project {project_name} is not configured")
        raise DstackError(f"No default project")
    return APIClient(project.url, project.token), project.name
