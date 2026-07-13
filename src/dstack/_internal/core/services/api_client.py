import os
from typing import Optional, Tuple

import dstack._internal.core.services.configs as configs
from dstack._internal.core.consts import (
    DSTACK_PROJECT_ENV,
    DSTACK_SERVER_URL_ENV,
    DSTACK_TOKEN_ENV,
)
from dstack._internal.core.errors import ConfigurationError
from dstack.api.server import APIClient


def get_api_client(project_name: Optional[str] = None) -> Tuple[APIClient, str]:
    env_project_name = project_name or os.getenv(DSTACK_PROJECT_ENV)
    server_url = os.getenv(DSTACK_SERVER_URL_ENV)
    token = os.getenv(DSTACK_TOKEN_ENV)
    if server_url is not None and token is not None:
        if env_project_name is None:
            raise ConfigurationError(
                f"{DSTACK_SERVER_URL_ENV} and {DSTACK_TOKEN_ENV} are set,"
                f" but the project is not specified."
                f" Set {DSTACK_PROJECT_ENV} or use --project"
            )
        return APIClient(server_url, token), env_project_name

    config = configs.ConfigManager()
    project = config.get_project_config(project_name)
    if project is None:
        if server_url is not None:
            raise ConfigurationError(
                f"{DSTACK_SERVER_URL_ENV} is set, but {DSTACK_TOKEN_ENV} is not set"
            )
        if project_name is not None:
            raise ConfigurationError(f"Project {project_name} is not configured")
        raise ConfigurationError("No default project, specify project name")
    if token is not None:
        # DSTACK_TOKEN overrides the configured token
        return APIClient(project.url, token), project.name
    return APIClient(project.url, project.token), project.name
