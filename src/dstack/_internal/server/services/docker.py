import re
from dataclasses import dataclass
from typing import List, Optional

import requests
from dxf import DXF
from dxf.exceptions import DXFError
from pydantic import Field, ValidationError, validator
from typing_extensions import Annotated

from dstack._internal.core.errors import DockerRegistryError
from dstack._internal.core.models.common import CoreModel, RegistryAuth
from dstack._internal.server import settings as server_settings
from dstack._internal.server.utils.common import join_byte_stream_checked
from dstack._internal.utils.docker import (
    LEGACY_DEFAULT_REGISTRY,
    is_default_registry,
    parse_image_name,
)

DEFAULT_PLATFORM = "linux/amd64"
MAX_CONFIG_OBJECT_SIZE = 2**22  # 4 MiB
REGISTRY_REQUEST_TIMEOUT = 20


@dataclass
class DXFAuthAdapter:
    registry_auth: Optional[RegistryAuth]

    def __call__(self, dxf: DXF, response: requests.Response) -> None:
        dxf.authenticate(
            username=self.registry_auth.username if self.registry_auth else None,
            password=self.registry_auth.password if self.registry_auth else None,
            response=response,
        )


class ImageConfig(CoreModel):
    user: Annotated[Optional[str], Field(alias="User")] = None
    entrypoint: Annotated[Optional[List[str]], Field(alias="Entrypoint")] = None
    cmd: Annotated[Optional[List[str]], Field(alias="Cmd")] = None

    @validator("user")
    def normalize_user(cls, v: Optional[str]) -> Optional[str]:
        # If USER is not set, the corresponding field may be missing or set to an empty string
        if v == "":
            return None
        return v


class ImageConfigObject(CoreModel):
    config: ImageConfig = ImageConfig()

    @validator("config", pre=True)
    def config_set_default_if_null(cls, value):
        return ImageConfig() if value is None else value


class ImageManifestConfigField(CoreModel):
    digest: str


class ImageManifest(CoreModel):
    config: ImageManifestConfigField


def get_image_config(image_name: str, registry_auth: Optional[RegistryAuth]) -> ImageConfigObject:
    image = parse_image_name(image_name)

    registry = image.registry
    if registry is None or is_default_registry(registry):
        registry = LEGACY_DEFAULT_REGISTRY

    registry_client = DXF(
        host=registry,
        repo=image.repo,
        auth=DXFAuthAdapter(registry_auth),  # type: ignore[assignment]
        timeout=REGISTRY_REQUEST_TIMEOUT,
    )

    with registry_client:
        try:
            manifest_resp = registry_client.get_manifest(
                alias=image.digest or image.tag, platform=DEFAULT_PLATFORM
            )
            manifest = ImageManifest.__response__.parse_raw(manifest_resp)
            config_stream = registry_client.pull_blob(manifest.config.digest)
            config_resp = join_byte_stream_checked(config_stream, MAX_CONFIG_OBJECT_SIZE)  # type: ignore[arg-type]
            if config_resp is None:
                raise DockerRegistryError(
                    f"Image config object exceeds the size limit of {MAX_CONFIG_OBJECT_SIZE} bytes"
                )
            return ImageConfigObject.__response__.parse_raw(config_resp)

        except (DXFError, requests.RequestException, ValidationError) as e:
            raise DockerRegistryError(e)


def apply_server_docker_defaults(
    image_name: str,
    registry_auth: Optional[RegistryAuth],
) -> tuple[str, Optional[RegistryAuth]]:
    if parse_image_name(image_name).registry is not None:
        return image_name, registry_auth
    if server_settings.SERVER_DEFAULT_DOCKER_REGISTRY is not None:
        image_name = f"{server_settings.SERVER_DEFAULT_DOCKER_REGISTRY}/{image_name}"
    if (
        registry_auth is None
        and server_settings.SERVER_DEFAULT_DOCKER_REGISTRY_USERNAME is not None
        and server_settings.SERVER_DEFAULT_DOCKER_REGISTRY_PASSWORD is not None
    ):
        registry_auth = RegistryAuth(
            username=server_settings.SERVER_DEFAULT_DOCKER_REGISTRY_USERNAME,
            password=server_settings.SERVER_DEFAULT_DOCKER_REGISTRY_PASSWORD,
        )
    return image_name, registry_auth


DOCKER_TARGET_PATH_PATTERN = re.compile(r"^(/[^/\0]*)+/?$")


def is_valid_docker_volume_target(path: str) -> bool:
    if not path.startswith("/"):
        return False
    if path.endswith("/") and path != "/":
        return False
    return DOCKER_TARGET_PATH_PATTERN.match(path) is not None
