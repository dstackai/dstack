import re
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


def validate_image_name(image: str) -> None:
    """
    Validates an image reference, e.g., `ubuntu`, `ghcr.io/org/repo:tag`, `repo@sha256:...`,
    as the kubelet and container runtimes parse it.

    Raises:
        ValueError: The reference is invalid.
    """
    match = _REFERENCE_REGEX.fullmatch(image)
    if match is None:
        raise ValueError("Invalid reference format")
    digest = match.group("digest")
    if digest is None:
        return
    algorithm, encoded = digest.split(":", maxsplit=1)
    length = _DIGEST_ENCODED_LENGTHS.get(algorithm)
    if length is None:
        raise ValueError(f"Unsupported digest algorithm: {algorithm}")
    if re.fullmatch(rf"[a-f0-9]{{{length}}}", encoded) is None:
        raise ValueError(f"Invalid {algorithm} digest: must be {length} lowercase hex digits")


# The reference grammar of
# https://github.com/distribution/reference/blob/v0.6.0/regexp.go
_ALPHANUMERIC = r"[a-z0-9]+"
_SEPARATOR = r"(?:[._]|__|[-]+)"
_PATH_COMPONENT = rf"{_ALPHANUMERIC}(?:{_SEPARATOR}{_ALPHANUMERIC})*"
_DOMAIN_NAME_COMPONENT = r"(?:[a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9])"
_DOMAIN_NAME = rf"{_DOMAIN_NAME_COMPONENT}(?:\.{_DOMAIN_NAME_COMPONENT})*"
_IPV6_ADDRESS = r"\[(?:[a-fA-F0-9:]+)\]"
_DOMAIN_AND_PORT = rf"(?:{_DOMAIN_NAME}|{_IPV6_ADDRESS})(?::[0-9]+)?"
_REMOTE_NAME = rf"{_PATH_COMPONENT}(?:/{_PATH_COMPONENT})*"
_NAME = rf"(?:{_DOMAIN_AND_PORT}/)?{_REMOTE_NAME}"
_TAG = r"[\w][\w.-]{0,127}"
_DIGEST = r"[A-Za-z][A-Za-z0-9]*(?:[-_+.][A-Za-z][A-Za-z0-9]*)*:[0-9a-fA-F]{32,}"
_REFERENCE_REGEX = re.compile(
    rf"{_NAME}(?::{_TAG})?(?:@(?P<digest>{_DIGEST}))?",
    # \w is ASCII-only in Go
    re.ASCII,
)
# The algorithms that https://github.com/opencontainers/go-digest supports
_DIGEST_ENCODED_LENGTHS = {"sha256": 64, "sha384": 96, "sha512": 128}


def _is_host(s: str) -> bool:
    return s == "localhost" or ":" in s or "." in s
