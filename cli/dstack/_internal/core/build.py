from enum import Enum

from dstack._internal.core.error import DstackError


class DockerPlatform(str, Enum):
    amd64 = "amd64"
    arm64 = "arm64"


class BuildPlan(str, Enum):
    no = "no"
    use = "use"
    yes = "yes"


class BuildNotFoundError(DstackError):
    code = "build_not_found"
