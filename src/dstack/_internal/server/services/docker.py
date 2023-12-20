from enum import Enum
from typing import Optional

import requests
from pydantic import BaseModel

manifests_media_types = [
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
]


class DockerImage(BaseModel):
    class Config:
        frozen = True

    image: str
    registry: Optional[str]
    repo: str
    tag: str
    digest: Optional[str]


class DockerPlatform(str, Enum):
    x86 = "amd64"
    arm = "arm64"


class DockerRegistryClient:
    def __init__(self):
        self.registry: Optional[str] = None
        self.repo: Optional[str] = None
        self.s = requests.Session()

    def auth(self, repo: str, *, registry: Optional[str] = None, token: Optional[str] = None):
        self.registry = registry
        self.repo = repo

        if not token:
            auth_host = registry
            params = {"scope": f"repository:{repo}:pull"}
            if not registry:
                auth_host = "auth.docker.io"
                params["service"] = "registry.docker.io"

            r = requests.get(f"https://{auth_host}/token", params=params)
            r.raise_for_status()
            token = r.json()["token"]
        self.s.headers = {"Authorization": f"Bearer {token}"}

    def manifests(self, tag: str = "latest", *, accept: Optional[str] = None) -> dict:
        registry_host = self.registry or "registry-1.docker.io"
        r = self.s.get(
            f"https://{registry_host}/v2/{self.repo}/manifests/{tag}",
            headers={"Accept": accept or ",".join(manifests_media_types)},
        )
        r.raise_for_status()
        return r.json()

    def blobs(self, digest: str) -> dict:
        registry_host = self.registry or "registry-1.docker.io"
        r = self.s.get(f"https://{registry_host}/v2/{self.repo}/blobs/{digest}")
        r.raise_for_status()
        return r.json()


def get_image_config(
    image: str, *, platform: DockerPlatform = DockerPlatform.x86, token: Optional[str] = None
) -> dict:
    image = parse_image_name(image)
    client = DockerRegistryClient()
    client.auth(image.repo, registry=image.registry, token=token)

    manifest = client.manifests(image.digest or image.tag)
    if "config" not in manifest:  # manifest index/list, pick the right platform
        for m in manifest["manifests"]:
            if m["platform"]["architecture"] == platform.value:
                manifest = client.manifests(m["digest"], accept=m["mediaType"])
                break
        else:
            raise RuntimeError("No manifest for the specified platform")

    return client.blobs(manifest["config"]["digest"])


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
