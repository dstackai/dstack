from typing import List, Optional

import yaml
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceExistsError
from dstack._internal.core.models.backends import AnyConfigInfoWithCreds
from dstack._internal.server import settings
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import projects as projects_services


class ProjectConfig(BaseModel):
    name: str
    backends: List[AnyConfigInfoWithCreds]


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
