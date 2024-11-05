from typing import Dict, List, Optional

from dstack._internal.proxy.repos.base import BaseProxyRepo, ChatModel, Project, Service


class InMemoryProxyRepo(BaseProxyRepo):
    def __init__(self) -> None:
        self.services: Dict[str, Dict[str, Service]] = {}
        self.models: Dict[str, Dict[str, ChatModel]] = {}
        self.projects: Dict[str, Project] = {}

    async def get_service(self, project_name: str, run_name: str) -> Optional[Service]:
        return self.services.get(project_name, {}).get(run_name)

    async def add_service(self, project_name: str, service: Service) -> None:
        self.services.setdefault(project_name, {})[service.run_name] = service

    async def list_models(self, project_name: str) -> List[ChatModel]:
        return list(self.models.get(project_name, {}).values())

    async def get_model(self, project_name: str, name: str) -> Optional[ChatModel]:
        return self.models.get(project_name, {}).get(name)

    async def add_model(self, project_name: str, model: ChatModel) -> None:
        self.models.setdefault(project_name, {})[model.name] = model

    async def get_project(self, name: str) -> Optional[Project]:
        return self.projects.get(name)

    async def add_project(self, project: Project) -> None:
        self.projects[project.name] = project

    async def is_project_member(self, project_name: str, token: str) -> bool:
        # TODO(#1595): when this class is used for gateways,
        # implement a network request to dstack-server to check authorization
        raise NotImplementedError
