from enum import Enum

from dstack._internal.core.error import DstackError


class BuildPolicy(str, Enum):
    USE_BUILD = "use-build"
    BUILD = "build"
    FORCE_BUILD = "force-build"
    BUILD_ONLY = "build-only"


class DockerPlatform(str, Enum):
    amd64 = "amd64"
    arm64 = "arm64"


class BuildPlan(str, Enum):
    no = "no"
    use = "use"
    yes = "yes"


class BuildNotFoundError(DstackError):
    code = "build_not_found"
