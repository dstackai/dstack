from enum import Enum
from typing import Tuple

import requests


class DockerPlatform(str, Enum):
    x86 = "amd64"
    arm = "arm64"


class DockerRegistryClient:
    def __init__(self):
        self.repo = None
        self.token = None

    def auth(self, repo: str):
        auth_host = "auth.docker.io"  # todo ghcr.io
        service = "registry.docker.io"
        r = requests.get(
            f"https://{auth_host}/token",
            params={
                "service": service,
                "scope": f"repository:{repo}:pull",
            },
        )
        r.raise_for_status()
        self.repo = repo
        self.token = r.json()["token"]

    def manifests(
        self, tag: str = "latest", *, accept="application/vnd.docker.distribution.manifest.v2+json"
    ) -> dict:
        registry_host = "registry-1.docker.io"
        r = requests.get(
            f"https://{registry_host}/v2/{self.repo}/manifests/{tag}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": accept,
            },
        )
        r.raise_for_status()
        return r.json()

    def blobs(self, digest: str) -> dict:
        registry_host = "registry-1.docker.io"
        r = requests.get(
            f"https://{registry_host}/v2/{self.repo}/blobs/{digest}",
            headers={
                "Authorization": f"Bearer {self.token}",
            },
        )
        r.raise_for_status()
        return r.json()


def get_image_config(image: str, platform: DockerPlatform = DockerPlatform.x86) -> dict:
    _, repo, tag = parse_image_name(image)
    # todo ghcr.io
    client = DockerRegistryClient()
    client.auth(repo)

    manifest = client.manifests(tag)
    if "config" not in manifest:
        for m in manifest["manifests"]:
            if m["platform"]["architecture"] == platform.value:
                manifest = client.manifests(m["digest"], accept=m["mediaType"])
                break

    return client.blobs(manifest["config"]["digest"])


def parse_image_name(image: str) -> Tuple[str, str, str]:
    """
    :param image: docker image name
    :return: registry host, repository, tag

    >>> parse_image_name("ubuntu:22.04")
    ('', 'library/ubuntu', '22.04')
    >>> parse_image_name("dstackai/miniforge:py3.9-0.2")
    ('', 'dstackai/miniforge', 'py3.9-0.2')
    >>> parse_image_name("ghcr.io/dstackai/miniforge")
    ('ghcr.io', 'dstackai/miniforge', 'latest')
    >>> parse_image_name("dstackai/miniforge@sha256:a4ba18a847a172a248d68faf6689e69fae4779b90b250211b79a26d21ddd6a15")
    ('', 'dstackai/miniforge', 'sha256:a4ba18a847a172a248d68faf6689e69fae4779b90b250211b79a26d21ddd6a15')
    """
    parts = image.split("/")
    if len(parts) == 1 or (
        parts[0] != "localhost" and ":" not in parts[0] and "." not in parts[0]
    ):
        host = ""
        repo_tag = "library/" + parts[0] if len(parts) == 1 else "/".join(parts)
    else:
        host = parts[0]
        repo_tag = "/".join(parts[1:])
    if "@" in repo_tag:
        repo, tag = repo_tag.split("@")
    else:
        repo, tag = repo_tag.split(":") if ":" in repo_tag else (repo_tag, "latest")
    return host, repo, tag
