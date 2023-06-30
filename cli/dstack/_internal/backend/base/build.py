import hashlib
from enum import Enum
from pathlib import Path
from typing import Tuple

import requests

from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.error import DstackError
from dstack._internal.core.job import Job


class DockerPlatform(str, Enum):
    x86 = "amd64"
    arm = "arm64"


def build_satisfied(storage: Storage, job: Job) -> bool:
    if not job.build_commands:
        return True
    if job.build_policy != "use-build":
        return True

    if job.registry_auth:
        return True  # todo
    try:
        digest = _get_build_digest(job)
    except RegistryNotSupportedError:
        return True  # todo

    builds = storage.list_objects(f"builds/{job.repo_ref.repo_id}/{digest}")
    if len(builds) > 0:
        return True
    return False


def _get_image_digest(image: str, platform: DockerPlatform) -> str:
    host, repo, tag = _parse_image_name(image)
    if host:
        raise RegistryNotSupportedError(
            "Can't check if build exists for base image from custom registry"
        )
    else:
        host = "index.docker.io"
        auth_host = "auth.docker.io"
        auth_params = {"service": "registry.docker.io"}

    auth_params["scope"] = f"repository:{repo}:pull"
    r = requests.get(f"https://{auth_host}/token", params=auth_params)
    r.raise_for_status()
    token = r.json()["token"]

    r = requests.get(
        f"https://{host}/v2/{repo}/manifests/{tag}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.distribution.manifest.list.v2+json",
        },
    )
    r.raise_for_status()
    manifests = r.json()["manifests"]

    for m in manifests:
        if m["platform"]["architecture"] == platform.value:
            platform_sha = m["digest"]
            break
    else:
        raise PlatformNotFoundError(
            f"Platform `{platform.value}` not found for the image {repo}:{tag}."
        )
    r = requests.get(
        f"https://{host}/v2/{repo}/manifests/{platform_sha}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
        },
    )
    r.raise_for_status()
    config = r.json()["config"]
    return config["digest"]


def _parse_image_name(image: str) -> Tuple[str, str, str]:
    """
    :param image: docker image name
    :return: registry host, repository, tag

    >>> _parse_image_name("ubuntu:22.04")
    ('', 'library/ubuntu', '22.04')
    >>> _parse_image_name("dstackai/miniforge:py3.9-0.2")
    ('', 'dstackai/miniforge', 'py3.9-0.2')
    >>> _parse_image_name("ghcr.io/dstackai/miniforge")
    ('ghcr.io', 'dstackai/miniforge', 'latest')
    >>> _parse_image_name("dstackai/miniforge@sha256:a4ba18a847a172a248d68faf6689e69fae4779b90b250211b79a26d21ddd6a15")
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


def _get_build_digest(job: Job, platform: DockerPlatform = DockerPlatform.x86) -> str:
    parts = [
        _get_image_digest(job.image_name, platform),
        (Path("/workflow") / (job.working_dir or "")).as_posix(),
        job.configuration_path,
        job.configuration_type,
        "",
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


class PlatformNotFoundError(DstackError):
    pass


class RegistryNotSupportedError(DstackError):
    pass


class BuildNotFoundError(DstackError):
    pass
