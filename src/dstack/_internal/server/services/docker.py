import contextlib
import re
from dataclasses import dataclass
from typing import List, Optional

import gpuhunt
import requests
from dxf import DXF
from dxf.exceptions import DXFError
from pydantic import Field, ValidationError, field_validator
from typing_extensions import Annotated

from dstack._internal.core.errors import DockerRegistryError
from dstack._internal.core.models.common import CoreModel, RegistryAuth, validate_json_extra_ignore
from dstack._internal.server import settings as server_settings
from dstack._internal.server.utils.common import join_byte_stream_checked
from dstack._internal.utils.docker import (
    LEGACY_DEFAULT_REGISTRY,
    is_default_registry,
    parse_image_name,
)

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

    @field_validator("user")
    @classmethod
    def normalize_user(cls, v: Optional[str]) -> Optional[str]:
        # If USER is not set, the corresponding field may be missing or set to an empty string
        if v == "":
            return None
        return v


class ImageConfigObject(CoreModel):
    architecture: str
    os: str
    config: ImageConfig = ImageConfig()

    @field_validator("config", mode="before")
    @classmethod
    def config_set_default_if_null(cls, value):
        return ImageConfig() if value is None else value


class ImageManifestConfigField(CoreModel):
    digest: str


class ImageManifest(CoreModel):
    config: ImageManifestConfigField


def get_image_config_and_cpu_architectures(
    image_name: str, registry_auth: Optional[RegistryAuth]
) -> tuple[ImageConfigObject, set[gpuhunt.CPUArchitecture]]:
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
        cpu_architectures: Optional[set[gpuhunt.CPUArchitecture]] = None
        try:
            # FIXME: get_manifest() makes N+1 requests when platform is not specified and alias
            # points to an image index, where N is a number of images in the index,
            # e.g., debian has 8 os/architecture[/variant] combinations
            manifest_resp = registry_client.get_manifest(alias=image.digest or image.tag)
            if isinstance(manifest_resp, dict):
                # Image index (OCI) aka Manifest list (Docker) -- multi os/arch higher-level object
                manifests: dict[gpuhunt.CPUArchitecture, ImageManifest] = {}
                for platform, manifest_raw in manifest_resp.items():
                    # os/architecture[/variant]
                    os_name, architecture, *_ = platform.split("/")
                    if not _os_supported(os_name):
                        continue
                    cpu_arch = _cpu_arch_from_string(architecture)
                    if cpu_arch is not None:
                        manifests[cpu_arch] = validate_json_extra_ignore(
                            ImageManifest, manifest_raw
                        )
                # ImageConfigs (User/Cmd/Entrypoint) may be different for different images
                # within the same index; we assume that it's not the case but at least pick
                # the manifest deterministically
                for cpu_arch in [gpuhunt.CPUArchitecture.X86, gpuhunt.CPUArchitecture.ARM]:
                    with contextlib.suppress(KeyError):
                        manifest = manifests[cpu_arch]
                        break
                else:
                    raise _no_supported_platforms_error(image_name)
                cpu_architectures = set(manifests)
            else:
                # Image manifest -- one specific os/arch combination
                manifest = validate_json_extra_ignore(ImageManifest, manifest_resp)

            config_stream = registry_client.pull_blob(manifest.config.digest)
            config_resp = join_byte_stream_checked(config_stream, MAX_CONFIG_OBJECT_SIZE)  # type: ignore[arg-type]
            if config_resp is None:
                raise DockerRegistryError(
                    f"Image config object exceeds the size limit of {MAX_CONFIG_OBJECT_SIZE} bytes"
                )
            image_config = validate_json_extra_ignore(ImageConfigObject, config_resp)

            if cpu_architectures is None:
                cpu_arch = _cpu_arch_from_string(image_config.architecture)
                if not _os_supported(image_config.os) or cpu_arch is None:
                    raise _no_supported_platforms_error(image_name)
                cpu_architectures = {cpu_arch}

            return image_config, cpu_architectures

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


def _cpu_arch_from_string(architecture: str) -> Optional[gpuhunt.CPUArchitecture]:
    if architecture == "amd64":
        return gpuhunt.CPUArchitecture.X86
    if architecture == "arm64":
        return gpuhunt.CPUArchitecture.ARM
    return None


def _os_supported(os_name: str) -> bool:
    return os_name == "linux"


def _no_supported_platforms_error(image_name: str) -> DockerRegistryError:
    return DockerRegistryError(f"No supported OS/architectures found: {image_name!r}")
