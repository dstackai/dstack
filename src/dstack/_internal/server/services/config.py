from pathlib import Path
from typing import List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, root_validator
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from dstack._internal.core.models.backends import AnyConfigInfoWithCreds
from dstack._internal.core.models.backends.aws import AnyAWSCreds
from dstack._internal.core.models.backends.azure import AnyAzureCreds
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.cudo import AnyCudoCreds
from dstack._internal.core.models.backends.datacrunch import AnyDataCrunchCreds
from dstack._internal.core.models.backends.kubernetes import KubernetesNetworkingConfig
from dstack._internal.core.models.backends.lambdalabs import AnyLambdaCreds
from dstack._internal.core.models.backends.runpod import AnyRunpodCreds
from dstack._internal.core.models.backends.tensordock import AnyTensorDockCreds
from dstack._internal.core.models.backends.vastai import AnyVastAICreds
from dstack._internal.core.models.common import CoreModel
from dstack._internal.server import settings
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import projects as projects_services
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class AWSConfig(CoreModel):
    type: Annotated[Literal["aws"], Field(description="The type of the backend")] = "aws"
    regions: Optional[List[str]] = None
    vpc_name: Annotated[Optional[str], Field(description="The VPC name")] = None
    creds: AnyAWSCreds = Field(..., description="The credentials", discriminator="type")


class AzureConfig(CoreModel):
    type: Annotated[Literal["azure"], Field(description="The type of the backend")] = "azure"
    tenant_id: Annotated[str, Field(description="The tenant ID")]
    subscription_id: Annotated[str, Field(description="The subscription ID")]
    regions: Optional[List[str]] = None
    creds: AnyAzureCreds = Field(..., description="The credentials", discriminator="type")


class CudoConfig(CoreModel):
    type: Annotated[Literal["cudo"], Field(description="The type of backend")] = "cudo"
    regions: Optional[List[str]] = None
    creds: Annotated[AnyCudoCreds, Field(description="The credentials")]
    project_id: Annotated[str, Field(description="The project ID")]


class DataCrunchConfig(CoreModel):
    type: Annotated[Literal["datacrunch"], Field(description="The type of backend")] = "datacrunch"
    regions: Optional[List[str]] = None
    creds: Annotated[AnyDataCrunchCreds, Field(description="The credentials")]


class GCPServiceAccountCreds(CoreModel):
    type: Annotated[Literal["service_account"], Field(description="The type of credentials")] = (
        "service_account"
    )
    filename: Annotated[str, Field(description="The path to the service account file")]
    # If data is None, it is read from the file
    data: Annotated[
        Optional[str], Field(description="The contents of the service account file")
    ] = None

    @root_validator
    def fill_data(cls, values):
        return _fill_data(values)


class GCPDefaultCreds(CoreModel):
    type: Annotated[Literal["default"], Field(description="The type of credentials")] = "default"


AnyGCPCreds = Union[GCPServiceAccountCreds, GCPDefaultCreds]


class GCPConfig(CoreModel):
    type: Annotated[Literal["gcp"], Field(description="The type of backend")] = "gcp"
    project_id: Annotated[str, Field(description="The project ID")]
    regions: Optional[List[str]] = None
    creds: AnyGCPCreds = Field(..., description="The credentials", discriminator="type")


class KubeconfigConfig(CoreModel):
    filename: Annotated[str, Field(description="The path to the kubeconfig file")]
    data: Annotated[Optional[str], Field(description="The contents of the kubeconfig file")] = None

    @root_validator
    def fill_data(cls, values):
        return _fill_data(values)


class KubernetesConfig(CoreModel):
    type: Annotated[Literal["kubernetes"], Field(description="The type of backend")] = "kubernetes"
    kubeconfig: Annotated[KubeconfigConfig, Field(description="The kubeconfig configuration")]
    networking: Annotated[
        Optional[KubernetesNetworkingConfig], Field(description="The networking configuration")
    ]


class LambdaConfig(CoreModel):
    type: Annotated[Literal["lambda"], Field(description="The type of backend")] = "lambda"
    regions: Optional[List[str]] = None
    creds: Annotated[AnyLambdaCreds, Field(description="The credentials")]


class NebiusServiceAccountCreds(CoreModel):
    type: Annotated[Literal["service_account"], Field(description="The type of credentials")] = (
        "service_account"
    )
    filename: Annotated[str, Field(description="The path to the service account file")]
    data: Annotated[
        Optional[str], Field(description="The contents of the service account file")
    ] = None

    @root_validator
    def fill_data(cls, values):
        return _fill_data(values)


AnyNebiusCreds = Union[NebiusServiceAccountCreds]


class NebiusConfig(CoreModel):
    type: Literal["nebius"] = "nebius"
    cloud_id: str
    folder_id: str
    network_id: str
    regions: Optional[List[str]] = None
    creds: AnyNebiusCreds


class RunpodConfig(CoreModel):
    type: Literal["runpod"] = "runpod"
    regions: Optional[List[str]] = None
    creds: AnyRunpodCreds


class TensorDockConfig(CoreModel):
    type: Annotated[Literal["tensordock"], Field(description="The type of backend")] = "tensordock"
    regions: Optional[List[str]] = None
    creds: Annotated[AnyTensorDockCreds, Field(description="The credentials")]


class VastAIConfig(CoreModel):
    type: Annotated[Literal["vastai"], Field(description="The type of backend")] = "vastai"
    regions: Optional[List[str]] = None
    creds: Annotated[AnyVastAICreds, Field(description="The credentials")]


class DstackConfig(CoreModel):
    type: Annotated[Literal["dstack"], Field(description="The type of backend")] = "dstack"


AnyBackendConfig = Union[
    AWSConfig,
    AzureConfig,
    CudoConfig,
    DataCrunchConfig,
    GCPConfig,
    KubernetesConfig,
    LambdaConfig,
    NebiusConfig,
    RunpodConfig,
    TensorDockConfig,
    VastAIConfig,
    DstackConfig,
]


BackendConfig = Annotated[AnyBackendConfig, Field(..., discriminator="type")]


class ProjectConfig(CoreModel):
    name: Annotated[str, Field(description="The name of the project")]
    backends: Annotated[List[BackendConfig], Field(description="The list of backends")]


class ServerConfig(CoreModel):
    projects: Annotated[List[ProjectConfig], Field(description="The list of projects")]


class ServerConfigManager:
    def load_config(self) -> bool:
        self.config = self._load_config()
        return self.config is not None

    async def init_config(self, session: AsyncSession):
        self.config = await self._init_config(session=session, init_backends=True)
        if self.config is not None:
            self._save_config(self.config)

    async def sync_config(self, session: AsyncSession):
        # Disable config.yml sync for https://github.com/dstackai/dstack/issues/815.
        return
        # self.config = await self._init_config(session=session, init_backends=False)
        # if self.config is not None:
        #     self._save_config(self.config)

    async def apply_config(self, session: AsyncSession, owner: UserModel):
        if self.config is None:
            raise ValueError("Config is not loaded")
        for project_config in self.config.projects:
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
            backends_to_delete = backends_services.list_available_backend_types()
            for backend_config in project_config.backends:
                config_info = _config_to_internal_config(backend_config)
                backend_type = BackendType(config_info.type)
                try:
                    backends_to_delete.remove(backend_type)
                except ValueError:
                    continue
                current_config_info = await backends_services.get_config_info(
                    project=project,
                    backend_type=backend_type,
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
                backends.append(_internal_config_to_config(config_info))
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
                    backends.append(_internal_config_to_config(config_info))
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
            yaml.dump(config.dict(exclude_none=True), f, sort_keys=False)


server_config_manager = ServerConfigManager()


class _BackendConfig(BaseModel):
    __root__: BackendConfig


def _internal_config_to_config(config_info: AnyConfigInfoWithCreds) -> BackendConfig:
    backend_config = _BackendConfig.parse_obj(config_info.dict(exclude={"locations"}))
    if config_info.type == "azure":
        backend_config.__root__.regions = config_info.locations
    return backend_config.__root__


class _ConfigInfoWithCreds(CoreModel):
    __root__: Annotated[AnyConfigInfoWithCreds, Field(..., discriminator="type")]


def _config_to_internal_config(backend_config: BackendConfig) -> AnyConfigInfoWithCreds:
    backend_config_dict = backend_config.dict()
    # Allow to not specify networking
    if backend_config.type == "kubernetes":
        if backend_config.networking is None:
            backend_config_dict["networking"] = {}
    if backend_config.type == "azure":
        backend_config_dict["locations"] = backend_config_dict["regions"]
        del backend_config_dict["regions"]
    config_info = _ConfigInfoWithCreds.parse_obj(backend_config_dict)
    return config_info.__root__


def _fill_data(values: dict):
    if values.get("data") is not None:
        return values
    if "filename" not in values:
        raise ValueError()
    try:
        with open(Path(values["filename"]).expanduser()) as f:
            values["data"] = f.read()
    except OSError:
        raise ValueError(f"No such file {values['filename']}")
    return values
