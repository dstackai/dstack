from typing import List, Optional

import yaml
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ConfigurationError, ResourceExistsError
from dstack._internal.core.models.backends import AnyConfigInfoWithCreds
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import gateways
from dstack._internal.server.services import projects as projects_services
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class GatewayConfig(BaseModel):
    name: str = settings.DEFAULT_GATEWAY_NAME
    backend: BackendType
    region: str
    wildcard_domain: Optional[str]


class ProjectConfig(BaseModel):
    name: str
    backends: List[AnyConfigInfoWithCreds]
    gateway: Optional[GatewayConfig]


class ServerConfig(BaseModel):
    projects: List[ProjectConfig]


class ServerConfigManager:
    def __init__(self) -> None:
        self.config = self._load_config()
        if self.config is None:
            self.config = self._get_initial_config()
            self._save_config(self.config)

    async def apply_config(self, session: AsyncSession):
        # TODO Do not update backend if unchanged.
        # Backend configuration may take time (e.g. azure)
        for project_config in self.config.projects:
            project = await projects_services.get_project_model_by_name(
                session=session,
                project_name=project_config.name,
            )
            for backend_config in project_config.backends:
                try:
                    await backends_services.create_backend(
                        session=session, project=project, config=backend_config
                    )
                except ResourceExistsError:
                    await backends_services.update_backend(
                        session=session, project=project, config=backend_config
                    )
            if project_config.gateway is not None:
                await apply_gateway_config(session, project, project_config.gateway)

    def _get_initial_config(self) -> ServerConfig:
        return ServerConfig(
            projects=[ProjectConfig(name=settings.DEFAULT_PROJECT_NAME, backends=[])]
        )

    def _load_config(self) -> Optional[ServerConfig]:
        try:
            with open(settings.SERVER_CONFIG_FILE_PATH) as f:
                content = f.read()
        except OSError:
            return
        config_dict = yaml.load(content, yaml.FullLoader)
        return ServerConfig.parse_obj(config_dict)

    def _save_config(self, config: ServerConfig):
        with open(settings.SERVER_CONFIG_FILE_PATH, "w+") as f:
            yaml.dump(config.dict(), f)


async def apply_gateway_config(
    session: AsyncSession, project: ProjectModel, gateway_config: GatewayConfig
):
    gateway = await gateways.get_gateway_by_name(session, project, gateway_config.name)
    if gateway is None:
        logger.info("Creating a new gateway from config.yaml")
        gateway = await gateways.create_gateway(
            session=session,
            project=project,
            name=gateway_config.name,
            backend_type=gateway_config.backend,
            region=gateway_config.region,
        )
    elif gateway.backend != gateway_config.backend:
        raise ConfigurationError(
            "Gateway backend cannot be changed. Delete the gateway or choose a new name."
        )

    await gateways.set_gateway_wildcard_domain(
        session, project, gateway.name, gateway_config.wildcard_domain
    )
    await gateways.set_default_gateway(session, project, gateway.name)
