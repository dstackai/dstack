from typing import Annotated, Literal, Optional, Union

from pydantic import Field, root_validator

from dstack._internal.core.backends.base.models import fill_data
from dstack._internal.core.models.common import CoreModel


class SlurmGPUPartitionConfig(CoreModel):
    gpu: Annotated[
        str,
        Field(
            description=(
                "The GPU model, in the `[vendor:]name[:memory]` format, e.g., `H200`, `A100:40GB`, `MI300X`"
            )
        ),
    ]
    partitions: Annotated[
        list[str], Field(description="The list of partitions with the specified GPU model")
    ]


class SlurmPrivateKeyConfig(CoreModel):
    path: Annotated[str, Field(description="The path to the private key file")] = ""
    content: Annotated[str, Field(description="The contents of the private key file")]


# `BaseSlurmClusterConfig` holds only non-sensitive fields safe to return in without-creds API
# responses. Connection details (hostname/port/user) and the private key are sensitive and live
# in `BaseSlurmClusterConfigWithCreds`/the creds-bearing configs instead.
#
# The credentialless `SlurmClusterConfig` and the creds-bearing configs are siblings, not
# parent/child. If the latter subclassed the former, a `list[SlurmClusterConfig]` field would
# accept a creds-bearing instance as-is (isinstance passthrough) and leak the sensitive fields
# into the without-creds API response instead of dropping them on re-validation.
class BaseSlurmClusterConfig(CoreModel):
    name: Annotated[str, Field(description="The name of the cluster. Used as a region name")]
    gpu_partitions: Annotated[
        Optional[list[SlurmGPUPartitionConfig]],
        Field(
            description=(
                "The mapping of GPU models to partitions."
                " Only partitions listed here are considered for GPU jobs."
                " If not set, GPU jobs are not allowed"
            ),
        ),
    ] = None
    cpu_partitions: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "Partitions considered for CPU jobs."
                " Defaults to all cluster partitions except those listed in `gpu_partitions`"
            ),
        ),
    ] = None


class SlurmClusterConfig(BaseSlurmClusterConfig):
    pass


class BaseSlurmClusterConfigWithCreds(BaseSlurmClusterConfig):
    hostname: Annotated[str, Field(description="The hostname or IP address of the login node")]
    port: Annotated[Optional[int], Field(description="The SSH port of the login node")] = None
    user: Annotated[str, Field(description="The user to log in to the login node")]


class SlurmClusterConfigWithCreds(BaseSlurmClusterConfigWithCreds):
    private_key: Annotated[SlurmPrivateKeyConfig, Field(description="The private key of the user")]


# Unlike other backends, `SlurmBackendConfigWithCreds` does not subclass `SlurmBackendConfig`:
# `clusters` differs in item type and `list` is invariant, so overriding it in a subclass is a
# type error. The two configs share only `type`, so they are kept as independent classes.
class SlurmBackendConfig(CoreModel):
    type: Annotated[
        Literal["slurm"],
        Field(description="The type of backend"),
    ] = "slurm"
    clusters: Annotated[list[SlurmClusterConfig], Field(description="Cluster configurations")]


class SlurmBackendConfigWithCreds(CoreModel):
    type: Annotated[
        Literal["slurm"],
        Field(description="The type of backend"),
    ] = "slurm"
    clusters: Annotated[
        list[SlurmClusterConfigWithCreds], Field(description="Cluster configurations")
    ]


class SlurmPrivateKeyFileConfig(CoreModel):
    path: Annotated[str, Field(description="The path to the private key file")] = ""
    content: Annotated[
        Optional[str],
        Field(
            description=(
                "The contents of the private key file."
                " When configuring via `server/config.yml`, it's automatically filled from `path`."
                " When configuring via UI, it has to be specified explicitly"
            )
        ),
    ] = None

    @root_validator
    def fill_data(cls, values: dict) -> dict:
        return fill_data(values, filename_field="path", data_field="content")


class SlurmClusterFileConfig(BaseSlurmClusterConfigWithCreds):
    private_key: Annotated[
        SlurmPrivateKeyFileConfig, Field(description="The private key of the user")
    ]


class SlurmBackendFileConfigWithCreds(CoreModel):
    type: Annotated[
        Literal["slurm"],
        Field(description="The type of backend"),
    ] = "slurm"
    clusters: Annotated[list[SlurmClusterFileConfig], Field(description="Cluster configurations")]


AnySlurmBackendConfig = Union[SlurmBackendConfig, SlurmBackendConfigWithCreds]


class SlurmStoredConfig(SlurmBackendConfigWithCreds):
    pass


class SlurmConfig(SlurmStoredConfig):
    pass
