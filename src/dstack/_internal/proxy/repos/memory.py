from typing import Dict, Optional

from dstack._internal.proxy.repos.base import BaseProxyRepo, Project, Service


class InMemoryProxyRepo(BaseProxyRepo):
    def __init__(self) -> None:
        self.services: Dict[str, Dict[str, Service]] = {}
        self.projects: Dict[str, Project] = {}

    async def get_service(self, project_name: str, run_name: str) -> Optional[Service]:
        return self.services.get(project_name, {}).get(run_name)

    async def add_service(self, project_name: str, service: Service) -> None:
        self.services.setdefault(project_name, {})[service.run_name] = service

    async def get_project(self, name: str) -> Optional[Project]:
        return self.projects.get(name)

    async def add_project(self, project: Project) -> None:
        self.projects[project.name] = project

    async def is_project_member(self, project_name: str, token: str) -> bool:
        # TODO(#1595): when this class is used for gateways,
        # implement a network request to dstack-server to check authorization
        raise NotImplementedError
