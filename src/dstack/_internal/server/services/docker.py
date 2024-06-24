import re
from dataclasses import dataclass
from typing import List, Optional

import requests
from dxf import DXF
from dxf.exceptions import DXFError
from pydantic import Field, ValidationError, validator
from typing_extensions import Annotated

from dstack._internal.core.errors import DockerRegistryError
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import RegistryAuth
from dstack._internal.server.utils.common import join_byte_stream_checked

DEFAULT_PLATFORM = "linux/amd64"
DEFAULT_REGISTRY = "index.docker.io"
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


class DockerImage(CoreModel):
    class Config:
        frozen = True

    image: str
    registry: Optional[str]
    repo: str
    tag: str
    digest: Optional[str]


class ImageConfig(CoreModel):
    entrypoint: Annotated[Optional[List[str]], Field(alias="Entrypoint")] = None
    cmd: Annotated[Optional[List[str]], Field(alias="Cmd")] = None


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

    registry_client = DXF(
        host=image.registry or DEFAULT_REGISTRY,
        repo=image.repo,
        auth=DXFAuthAdapter(registry_auth),
        timeout=REGISTRY_REQUEST_TIMEOUT,
    )

    with registry_client:
        try:
            manifest_resp = registry_client.get_manifest(
                alias=image.digest or image.tag, platform=DEFAULT_PLATFORM
            )
            manifest = ImageManifest.__response__.parse_raw(manifest_resp)
            config_stream = registry_client.pull_blob(manifest.config.digest)
            config_resp = join_byte_stream_checked(config_stream, MAX_CONFIG_OBJECT_SIZE)
            if config_resp is None:
                raise DockerRegistryError(
                    "Image config object exceeds the size limit of "
                    f"{MAX_CONFIG_OBJECT_SIZE} bytes"
                )
            return ImageConfigObject.__response__.parse_raw(config_resp)

        except (DXFError, requests.RequestException, ValidationError) as e:
            raise DockerRegistryError(e)


def parse_image_name(image: str) -> DockerImage:
    """
    :param image: docker image name
    :return: registry host, repo, tag, digest

    >>> parse_image_name("ubuntu:22.04")
    DockerImage(registry=None, repo='library/ubuntu', tag='22.04', digest=None)
    >>> parse_image_name("dstackai/miniforge:py3.9-0.2")
    DockerImage(registry=None, repo='dstackai/miniforge', tag='py3.9-0.2', digest=None)
    >>> parse_image_name("ghcr.io/dstackai/miniforge")
    DockerImage(registry='ghcr.io', repo='dstackai/miniforge', tag='latest', digest=None)
    >>> parse_image_name("dstackai/miniforge@sha256:a4ba18a847a172a248d68faf6689e69fae4779b90b250211b79a26d21ddd6a15")
    DockerImage(registry=None, repo='dstackai/miniforge', tag='latest', digest='sha256:a4ba18a847a172a248d68faf6689e69fae4779b90b250211b79a26d21ddd6a15')
    """

    digest = None
    if "@" in image.split("/")[-1]:
        image, digest = image.rsplit("@", maxsplit=1)

    tag = "latest"
    if ":" in image.split("/")[-1]:  # avoid detecting port as a tag
        image, tag = image.rsplit(":", maxsplit=1)

    registry = None
    components = image.split("/")
    if len(components) == 1:  # default registry, official image
        repo = "library/" + components[0]
    elif not is_host(components[0]):  # default registry, custom image
        repo = "/".join(components)
    else:  # custom registry
        registry = components[0]
        repo = "/".join(components[1:])

    return DockerImage(image=image, registry=registry, repo=repo, tag=tag, digest=digest)


def is_host(s: str) -> bool:
    """
    >>> is_host("localhost")
    True
    >>> is_host("localhost:5000")
    True
    >>> is_host("ghcr.io")
    True
    >>> is_host("127.0.0.1")
    True
    >>> is_host("dstackai")
    False
    """
    return s == "localhost" or ":" in s or "." in s


DOCKER_TARGET_PATH_PATTERN = re.compile(r"^(/[^/\0]*)+/?$")


def is_valid_docker_volume_target(path: str) -> bool:
    if not path.startswith("/"):
        return False
    if path.endswith("/") and path != "/":
        return False
    return DOCKER_TARGET_PATH_PATTERN.match(path) is not None
