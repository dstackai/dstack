from typing import List, Optional

import yaml
from pydantic import Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

import dstack._internal.core.backends.configurators
from dstack._internal.core.backends.models import (
    AnyBackendConfigWithCreds,
    AnyBackendFileConfigWithCreds,
    BackendInfoYAML,
)
from dstack._internal.core.errors import (
    BackendNotAvailable,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import encryption as encryption_services
from dstack._internal.server.services import projects as projects_services
from dstack._internal.server.services.backends.handlers import delete_backends_safe
from dstack._internal.server.services.encryption import AnyEncryptionKeyConfig
from dstack._internal.server.services.permissions import (
    DefaultPermissions,
    set_default_permissions,
)
from dstack._internal.server.services.plugins import load_plugins
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


# By default, PyYAML chooses the style of a collection depending on whether it has nested collections.
# If a collection has nested collections, it will be assigned the block style. Otherwise it will have the flow style.
#
# We want mapping to always be displayed in block-style but lists without nested objects in flow-style.
# So we define a custom representer.


def seq_representer(dumper, sequence):
    flow_style = len(sequence) == 0 or isinstance(sequence[0], str) or isinstance(sequence[0], int)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", sequence, flow_style)


yaml.add_representer(list, seq_representer)


BackendFileConfigWithCreds = Annotated[
    AnyBackendFileConfigWithCreds, Field(..., discriminator="type")
]


class ProjectConfig(CoreModel):
    name: Annotated[str, Field(description="The name of the project")]
    backends: Annotated[
        Optional[List[BackendFileConfigWithCreds]], Field(description="The list of backends")
    ] = None


EncryptionKeyConfig = Annotated[AnyEncryptionKeyConfig, Field(..., discriminator="type")]


class EncryptionConfig(CoreModel):
    keys: Annotated[List[EncryptionKeyConfig], Field(description="The encryption keys")]


class ServerConfig(CoreModel):
    projects: Annotated[List[ProjectConfig], Field(description="The list of projects")]
    encryption: Annotated[
        Optional[EncryptionConfig], Field(description="The encryption config")
    ] = None
    default_permissions: Annotated[
        Optional[DefaultPermissions], Field(description="The default user permissions")
    ] = None
    plugins: Annotated[
        Optional[List[str]], Field(description="The server-side plugins to enable")
    ] = None


class ServerConfigManager:
    def load_config(self) -> bool:
        self.config = self._load_config()
        return self.config is not None

    async def init_config(self, session: AsyncSession):
        """
        Initializes the default server/config.yml.
        The default config is empty or contains an existing `main` project config.
        """
        self.config = await self._init_config(session)
        if self.config is not None:
            self._save_config(self.config)

    async def sync_config(self, session: AsyncSession):
        # Disable config.yml sync for https://github.com/dstackai/dstack/issues/815.
        return

    async def apply_encryption(self):
        if self.config is None:
            logger.info("No server/config.yml. Skipping encryption configuration.")
            return
        if self.config.encryption is not None:
            encryption_services.init_encryption_keys(self.config.encryption.keys)

    async def apply_config(self, session: AsyncSession, owner: UserModel):
        if self.config is None:
            raise ValueError("Config is not loaded")
        if self.config.default_permissions is not None:
            set_default_permissions(self.config.default_permissions)
        for project_config in self.config.projects:
            await self._apply_project_config(
                session=session, owner=owner, project_config=project_config
            )
        load_plugins(enabled_plugins=self.config.plugins or [])

    async def _apply_project_config(
        self,
        session: AsyncSession,
        owner: UserModel,
        project_config: ProjectConfig,
    ):
        project = await projects_services.get_project_model_by_name(
            session=session,
            project_name=project_config.name,
        )
        if not project:
            await projects_services.create_project_model(
                session=session, owner=owner, project_name=project_config.name
            )
            project = await projects_services.get_project_model_by_name_or_error(
                session=session, project_name=project_config.name
            )
        backends_to_delete = set(
            dstack._internal.core.backends.configurators.list_available_backend_types()
        )
        for backend_file_config in project_config.backends or []:
            backend_config = file_config_to_config(backend_file_config)
            backend_type = BackendType(backend_config.type)
            backends_to_delete.difference_update([backend_type])
            try:
                current_backend_config = await backends_services.get_backend_config(
                    project=project,
                    backend_type=backend_type,
                )
            except BackendNotAvailable:
                logger.warning(
                    "Backend %s not available and won't be configured."
                    " Check that backend dependencies are installed.",
                    backend_type.value,
                )
                continue
            if backend_config == current_backend_config:
                continue
            backend_exists = any(backend_type == b.type for b in project.backends)
            try:
                # current_backend_config may be None if backend exists
                # but it's config is invalid (e.g. cannot be decrypted).
                # Update backend in this case.
                if current_backend_config is None and not backend_exists:
                    await backends_services.create_backend(
                        session=session, project=project, config=backend_config
                    )
                else:
                    await backends_services.update_backend(
                        session=session, project=project, config=backend_config
                    )
            except Exception as e:
                logger.warning("Failed to configure backend %s: %s", backend_config.type, e)
        await delete_backends_safe(
            session=session,
            project=project,
            backends_types=list(backends_to_delete),
            error=False,
        )

    async def _init_config(self, session: AsyncSession) -> Optional[ServerConfig]:
        project = await projects_services.get_project_model_by_name(
            session=session,
            project_name=settings.DEFAULT_PROJECT_NAME,
        )
        if project is None:
            return None
        # Force project reload to reflect updates when syncing
        await session.refresh(project)
        backends = []
        for (
            backend_type
        ) in dstack._internal.core.backends.configurators.list_available_backend_types():
            backend_config = await backends_services.get_backend_config(
                project=project, backend_type=backend_type
            )
            if backend_config is not None:
                backends.append(backend_config)
        return ServerConfig(
            projects=[ProjectConfig(name=settings.DEFAULT_PROJECT_NAME, backends=backends)],
            encryption=EncryptionConfig(keys=[]),
            default_permissions=None,
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
            f.write(config_to_yaml(config))


async def get_backend_config_yaml(
    project: ProjectModel, backend_type: BackendType
) -> BackendInfoYAML:
    backend_config = await backends_services.get_backend_config(
        project=project, backend_type=backend_type
    )
    if backend_config is None:
        raise ResourceNotExistsError()
    config_yaml = config_to_yaml(backend_config)
    return BackendInfoYAML(
        name=backend_type,
        config_yaml=config_yaml,
    )


async def create_backend_config_yaml(
    session: AsyncSession,
    project: ProjectModel,
    config_yaml: str,
):
    config = config_yaml_to_backend_config(config_yaml)
    await backends_services.create_backend(session=session, project=project, config=config)


async def update_backend_config_yaml(
    session: AsyncSession,
    project: ProjectModel,
    config_yaml: str,
):
    config = config_yaml_to_backend_config(config_yaml)
    await backends_services.update_backend(session=session, project=project, config=config)


class _BackendConfigWithCreds(CoreModel):
    """
    Model for parsing API and file YAML configs.
    """

    __root__: Annotated[AnyBackendConfigWithCreds, Field(..., discriminator="type")]


def config_yaml_to_backend_config(config_yaml: str) -> AnyBackendConfigWithCreds:
    try:
        config_dict = yaml.load(config_yaml, yaml.FullLoader)
    except yaml.YAMLError:
        raise ServerClientError("Error parsing YAML")
    try:
        backend_config = _BackendConfigWithCreds.parse_obj(config_dict).__root__
    except ValidationError as e:
        raise ServerClientError(str(e))
    return backend_config


def file_config_to_config(file_config: AnyBackendFileConfigWithCreds) -> AnyBackendConfigWithCreds:
    backend_config_dict = file_config.dict()
    backend_config = _BackendConfigWithCreds.parse_obj(backend_config_dict)
    return backend_config.__root__


def config_to_yaml(config: CoreModel) -> str:
    return yaml.dump(config.dict(exclude_none=True), sort_keys=False)
