from dataclasses import dataclass
from typing import Optional

# https://github.com/distribution/reference/blob/0965666a6ade2e06035fe352e38344be1e68951a/normalize.go#L11-L31
DEFAULT_REGISTRY = "docker.io"
LEGACY_DEFAULT_REGISTRY = "index.docker.io"


@dataclass(kw_only=True)
class DockerImage:
    image: str
    registry: Optional[str] = None
    repo: str
    tag: str
    digest: Optional[str] = None


def parse_image_name(image: str) -> DockerImage:
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
    elif not _is_host(components[0]):  # default registry, custom image
        repo = "/".join(components)
    else:  # custom registry
        registry = components[0]
        repo = "/".join(components[1:])

    return DockerImage(image=image, registry=registry, repo=repo, tag=tag, digest=digest)


def is_default_registry(registry: str) -> bool:
    return registry in [DEFAULT_REGISTRY, LEGACY_DEFAULT_REGISTRY]


def _is_host(s: str) -> bool:
    return s == "localhost" or ":" in s or "." in s
