from typing import List, Optional

import yaml
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends import AnyConfigInfoWithCreds
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import projects as projects_services
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class ProjectConfig(BaseModel):
    name: str
    backends: List[AnyConfigInfoWithCreds]


class ServerConfig(BaseModel):
    projects: List[ProjectConfig]


class ServerConfigManager:
    def load_config(self) -> bool:
        self.config = self._load_config()
        return self.config is not None

    async def init_config(self, session: AsyncSession):
        self.config = await self._init_config(session=session, init_backends=True)
        if self.config is not None:
            self._save_config(self.config)

    async def sync_config(self, session: AsyncSession):
        self.config = await self._init_config(session=session, init_backends=False)
        if self.config is not None:
            self._save_config(self.config)

    async def apply_config(self, session: AsyncSession):
        for project_config in self.config.projects:
            project = await projects_services.get_project_model_by_name(
                session=session,
                project_name=project_config.name,
            )
            backends_to_delete = backends_services.list_available_backend_types()
            for config_info in project_config.backends:
                backends_to_delete.remove(config_info.type)
                current_config_info = await backends_services.get_config_info(
                    project=project,
                    backend_type=config_info.type,
                )
                if config_info == current_config_info:
                    continue
                try:
                    if current_config_info is None:
                        await backends_services.create_backend(
                            session=session, project=project, config=config_info
                        )
                    else:
                        await backends_services.update_backend(
                            session=session, project=project, config=config_info
                        )
                except Exception as e:
                    logger.warning("Failed to configure backend %s: %s", config_info.type, e)
            await backends_services.delete_backends(
                session=session, project=project, backends_types=backends_to_delete
            )

    async def _init_config(
        self, session: AsyncSession, init_backends: bool
    ) -> Optional[ServerConfig]:
        project = await projects_services.get_project_model_by_name(
            session=session,
            project_name=settings.DEFAULT_PROJECT_NAME,
        )
        if project is None:
            return None
        # Force project reload to reflect updates when syncing
        await session.refresh(project)
        backends = []
        for backend_type in backends_services.list_available_backend_types():
            config_info = await backends_services.get_config_info(
                project=project, backend_type=backend_type
            )
            if config_info is not None:
                backends.append(config_info)
        if init_backends and len(backends) == 0:
            backends = await self._init_backends(session=session, project=project)
        return ServerConfig(
            projects=[ProjectConfig(name=settings.DEFAULT_PROJECT_NAME, backends=backends)]
        )

    async def _init_backends(
        self, session: AsyncSession, project: ProjectModel
    ) -> List[AnyConfigInfoWithCreds]:
        backends = []
        for backend_type in backends_services.list_available_backend_types():
            configurator = backends_services.get_configurator(backend_type)
            if configurator is None:
                continue
            config_infos = await run_async(configurator.get_default_configs)
            for config_info in config_infos:
                try:
                    await backends_services.create_backend(
                        session=session, project=project, config=config_info
                    )
                    backends.append(config_info)
                    break
                except Exception as e:
                    logger.debug("Failed to configure backend %s: %s", config_info.type, e)
        return backends

    def _load_config(self) -> Optional[ServerConfig]:
        try:
            with open(settings.SERVER_CONFIG_FILE_PATH) as f:
                content = f.read()
        except OSError:
            return
        config_dict = yaml.load(content, yaml.FullLoader)
        return ServerConfig.parse_obj(config_dict)

    def _save_config(self, config: ServerConfig):
        def seq_representer(dumper, sequence):
            flow_style = (
                len(sequence) == 0 or isinstance(sequence[0], str) or isinstance(sequence[0], int)
            )
            return dumper.represent_sequence("tag:yaml.org,2002:seq", sequence, flow_style)

        yaml.add_representer(list, seq_representer)

        with open(settings.SERVER_CONFIG_FILE_PATH, "w+") as f:
            yaml.dump(config.dict(), f, sort_keys=False)


server_config_manager = ServerConfigManager()
