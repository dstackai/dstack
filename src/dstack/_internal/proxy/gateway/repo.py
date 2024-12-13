from itertools import chain
from typing import Optional

from dstack._internal.proxy.gateway.models import GlobalProxyConfig
from dstack._internal.proxy.lib.models import ChatModel, Project, Service
from dstack._internal.proxy.lib.repo import BaseProxyRepo


class GatewayProxyRepo(BaseProxyRepo):
    def __init__(self) -> None:
        self.services: dict[str, dict[str, Service]] = {}
        self.models: dict[str, dict[str, ChatModel]] = {}
        self.projects: dict[str, Project] = {}
        self.config = GlobalProxyConfig()

    async def list_services(self) -> list[Service]:
        return list(
            chain(*(project_services.values() for project_services in self.services.values()))
        )

    async def get_service(self, project_name: str, run_name: str) -> Optional[Service]:
        return self.services.get(project_name, {}).get(run_name)

    async def set_service(self, service: Service) -> None:
        self.services.setdefault(service.project_name, {})[service.run_name] = service

    async def delete_service(self, project_name: str, run_name: str) -> None:
        project_services = self.services.get(project_name, {})
        project_services.pop(run_name, None)
        if not project_services:
            self.services.pop(project_name, None)

    async def list_models(self, project_name: str) -> list[ChatModel]:
        return list(self.models.get(project_name, {}).values())

    async def get_model(self, project_name: str, name: str) -> Optional[ChatModel]:
        return self.models.get(project_name, {}).get(name)

    async def set_model(self, model: ChatModel) -> None:
        self.models.setdefault(model.project_name, {})[model.name] = model

    async def delete_models_by_run(self, project_name: str, run_name: str) -> None:
        project_models = self.models.get(project_name, {})
        models_to_delete = [m for m in project_models.values() if m.run_name == run_name]
        for model in models_to_delete:
            project_models.pop(model.name, None)
        if not project_models:
            self.models.pop(project_name, None)

    async def get_project(self, name: str) -> Optional[Project]:
        return self.projects.get(name)

    async def set_project(self, project: Project) -> None:
        self.projects[project.name] = project

    async def get_config(self) -> GlobalProxyConfig:
        return self.config

    async def set_config(self, config: GlobalProxyConfig) -> None:
        self.config = config
