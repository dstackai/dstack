import tempfile
from contextlib import asynccontextmanager
from itertools import chain
from pathlib import Path
from typing import Iterable, Optional

from aiorwlock import RWLock
from pydantic import BaseModel

from dstack._internal.proxy.gateway.models import (
    GlobalProxyConfig,
    ImportedModel,
    ModelEntrypoint,
)
from dstack._internal.proxy.lib.models import ChatModel, OpenAIChatModelFormat, Project, Service
from dstack._internal.proxy.lib.repo import BaseProxyRepo
from dstack._internal.utils.common import run_async


class State(BaseModel):
    services: dict[str, dict[str, Service]] = {}
    models: dict[str, dict[str, ChatModel]] = {}
    imports: dict[str, dict[str, ImportedModel]] = {}
    """Importer project -> model name -> import."""
    entrypoints: dict[str, ModelEntrypoint] = {}
    projects: dict[str, Project] = {}
    config: GlobalProxyConfig = GlobalProxyConfig()


class GatewayProxyRepo(BaseProxyRepo):
    """
    Repo implementation used on gateways. Stores state in memory and maintains a copy on disk.
    """

    def __init__(self, state: Optional[State] = None, file: Optional[Path] = None) -> None:
        self._state = state or State()
        self._file = file
        self._lock = RWLock()

    async def list_services(self) -> list[Service]:
        async with self.reader():
            services_by_project = (
                project_services.values() for project_services in self._state.services.values()
            )
            return list(chain(*services_by_project))

    async def get_service(self, project_name: str, run_name: str) -> Optional[Service]:
        async with self.reader():
            return self._state.services.get(project_name, {}).get(run_name)

    async def get_service_by_domain(self, domain: str) -> Optional[Service]:
        async with self.reader():
            for project_services in self._state.services.values():
                for service in project_services.values():
                    if service.domain == domain:
                        return service
            return None

    async def set_service(self, service: Service) -> None:
        async with self.writer():
            self._state.services.setdefault(service.project_name, {})[service.run_name] = service

    async def set_services(self, services: Iterable[Service]) -> None:
        """Save a batch before publishing it, so failed saves remain retryable."""
        async with self._lock.writer:
            services_by_project = {
                name: entries.copy() for name, entries in self._state.services.items()
            }
            for service in services:
                services_by_project.setdefault(service.project_name, {})[service.run_name] = (
                    service
                )
            state = self._state.model_copy(update={"services": services_by_project})
            await run_async(self.save, state)
            self._state = state

    async def delete_service(self, project_name: str, run_name: str) -> None:
        async with self.writer():
            project_services = self._state.services.get(project_name, {})
            project_services.pop(run_name, None)
            if not project_services:
                self._state.services.pop(project_name, None)

    # Models are registered under lowercase project names (see `routers/registry.py`),
    # while the model proxy takes the project name from the request URL as the user typed it.

    async def list_models(self, project_name: str) -> list[ChatModel]:
        async with self.reader():
            project_name = project_name.lower()
            names = list(self._state.models.get(project_name, {}))
            names += list(self._state.imports.get(project_name, {}))
            # `dict.fromkeys` leaves each name once
            models = [self._get_model(project_name, name) for name in dict.fromkeys(names)]
            return [model for model in models if model is not None]

    async def get_model(self, project_name: str, name: str) -> Optional[ChatModel]:
        async with self.reader():
            return self._get_model(project_name.lower(), name)

    async def set_model(self, model: ChatModel) -> None:
        async with self.writer():
            self._state.models.setdefault(model.project_name, {})[model.name] = model

    async def delete_models_by_run(self, project_name: str, run_name: str) -> None:
        async with self.writer():
            project_models = self._state.models.get(project_name, {})
            models_to_delete = [m for m in project_models.values() if m.run_name == run_name]
            for model in models_to_delete:
                project_models.pop(model.name, None)
            if not project_models:
                self._state.models.pop(project_name, None)

    async def list_imports(self) -> list[ImportedModel]:
        async with self.reader():
            imports_by_project = (
                project_imports.values() for project_imports in self._state.imports.values()
            )
            return list(chain(*imports_by_project))

    async def set_import(self, imported_model: ImportedModel) -> None:
        """Replaces the project's import of the model, if it has one through another export."""
        async with self.writer():
            self._state.imports.setdefault(imported_model.importer_project, {})[
                imported_model.name
            ] = imported_model

    async def delete_import(self, importer_project: str, export_id: str, name: str) -> None:
        """Deletes the project's import of the model, unless it is through another export."""
        async with self.writer():
            project_imports = self._state.imports.get(importer_project, {})
            imported_model = project_imports.get(name)
            if imported_model is not None and imported_model.export_id == export_id:
                project_imports.pop(name)
            if not project_imports:
                self._state.imports.pop(importer_project, None)

    async def list_entrypoints(self) -> list[ModelEntrypoint]:
        async with self.reader():
            return list(self._state.entrypoints.values())

    async def set_entrypoint(self, entrypoint: ModelEntrypoint) -> None:
        async with self.writer():
            self._state.entrypoints[entrypoint.project_name] = entrypoint

    async def get_project(self, name: str) -> Optional[Project]:
        async with self.reader():
            return self._state.projects.get(name)

    async def set_project(self, project: Project) -> None:
        async with self.writer():
            self._state.projects[project.name] = project

    async def get_config(self) -> GlobalProxyConfig:
        async with self.reader():
            return self._state.config

    async def set_config(self, config: GlobalProxyConfig) -> None:
        async with self.writer():
            self._state.config = config

    @asynccontextmanager
    async def reader(self):
        async with self._lock.reader:
            yield

    @asynccontextmanager
    async def writer(self):
        async with self._lock.writer:
            yield
            await run_async(self.save)

    @staticmethod
    def load(state_file: Path) -> "GatewayProxyRepo":
        if state_file.exists():
            state = State.model_validate_json(state_file.read_text())
        else:
            state = None
        return GatewayProxyRepo(state=state, file=state_file)

    def save(self, state: Optional[State] = None) -> None:
        """Write the given state, or the current state, atomically."""
        if self._file is None:
            return
        if state is None:
            state = self._state
        with tempfile.NamedTemporaryFile(mode="w", dir=self._file.parent, delete=False) as f:
            temporary_path = Path(f.name)
            try:
                f.write(state.model_dump_json())
                f.close()
                temporary_path.replace(self._file)
            finally:
                temporary_path.unlink(missing_ok=True)

    def _get_model(self, project_name: str, name: str) -> Optional[ChatModel]:
        """
        Returns the project's own model with this name. If the project has none,
        returns the model that it imports under this name, with the export set.

        The import is skipped while the exporter project has no model with this name
        and the `openai` format, since only requests to models with this format are metered.
        """
        model = self._state.models.get(project_name, {}).get(name)
        if model is not None:
            return model
        imported_model = self._state.imports.get(project_name, {}).get(name)
        if imported_model is None:
            return None
        model = self._state.models.get(imported_model.exporter_project, {}).get(name)
        if model is None or not isinstance(model.format_spec, OpenAIChatModelFormat):
            return None
        return model.model_copy(update={"export_id": imported_model.export_id})
