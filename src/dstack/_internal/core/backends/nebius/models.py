import json
from pathlib import Path
from typing import Annotated, Dict, Literal, Optional, Union

from pydantic import Field, root_validator

from dstack._internal.core.backends.base.models import fill_data
from dstack._internal.core.models.common import CoreModel

DEFAULT_PROJECT_NAME_PREFIX = "default"


class NebiusServiceAccountCreds(CoreModel):
    type: Annotated[Literal["service_account"], Field(description="The type of credentials")] = (
        "service_account"
    )
    service_account_id: Annotated[str, Field(description="Service account ID")]
    public_key_id: Annotated[str, Field(description="ID of the service account public key")]
    private_key_file: Annotated[
        Optional[str], Field(description=("Path to the service account private key"))
    ] = None
    private_key_content: Annotated[
        str,
        Field(
            description=(
                "Content of the service account private key. When configuring via"
                " `server/config.yml`, it's automatically filled from `private_key_file`."
                " When configuring via UI, it has to be specified explicitly."
            )
        ),
    ]
    filename: Annotated[
        Optional[str], Field(description="The path to the service account credentials file")
    ] = None


class NebiusServiceAccountFileCreds(CoreModel):
    type: Annotated[Literal["service_account"], Field(description="The type of credentials")] = (
        "service_account"
    )
    service_account_id: Annotated[
        Optional[str],
        Field(
            description=(
                "Service account ID. Set automatically if `filename` is specified. When configuring via the UI, it must be specified explicitly"
            )
        ),
    ] = None
    public_key_id: Annotated[
        Optional[str],
        Field(
            description=(
                "ID of the service account public key. Set automatically if `filename` is specified. When configuring via the UI, it must be specified explicitly"
            )
        ),
    ] = None
    private_key_file: Annotated[
        Optional[str],
        Field(
            description=(
                "Path to the service account private key. Set automatically if `filename` or `private_key_content` is specified. When configuring via the UI, it must be specified explicitly"
            )
        ),
    ] = None
    private_key_content: Annotated[
        Optional[str],
        Field(
            description=(
                "Content of the service account private key. When configuring via"
                " `server/config.yml`, it's automatically filled from `private_key_file`."
                " When configuring via UI, it has to be specified explicitly"
            )
        ),
    ] = None
    filename: Annotated[
        Optional[str], Field(description="The path to the service account credentials file")
    ] = None

    @root_validator
    def fill_data(cls, values):
        if filename := values.get("filename"):
            try:
                with open(Path(filename).expanduser()) as f:
                    data = json.load(f)
                from nebius.base.service_account.credentials_file import (
                    ServiceAccountCredentials,
                )

                credentials = ServiceAccountCredentials.from_json(data)
                subject = credentials.subject_credentials
                values["service_account_id"] = subject.sub
                values["public_key_id"] = subject.kid
                values["private_key_content"] = subject.private_key
            except OSError:
                raise ValueError(f"No such file {filename}")
            except Exception as e:
                raise ValueError(f"Failed to parse credentials file {filename}: {e}")
            return values

        return fill_data(
            values, filename_field="private_key_file", data_field="private_key_content"
        )


AnyNebiusCreds = NebiusServiceAccountCreds
NebiusCreds = AnyNebiusCreds
AnyNebiusFileCreds = NebiusServiceAccountFileCreds


class NebiusBackendConfig(CoreModel):
    """
    The backend config used in the API, server/config.yml, `NebiusConfigurator`.
    It also serves as a base class for other backend config models.
    Should not include creds.
    """

    type: Annotated[
        Literal["nebius"],
        Field(description="The type of backend"),
    ] = "nebius"
    projects: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "The list of allowed Nebius project IDs."
                " Omit to use the default project in each region."
                " The project is considered default if it is the only project in the region"
                f" or if its name starts with `{DEFAULT_PROJECT_NAME_PREFIX}`"
            )
        ),
    ] = None
    regions: Annotated[
        Optional[list[str]],
        Field(description="The list of allowed Nebius regions. Omit to allow all regions"),
    ] = None
    fabrics: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "The list of allowed fabrics for InfiniBand clusters. Omit to allow all fabrics"
            )
        ),
    ] = None
    tags: Annotated[
        Optional[Dict[str, str]],
        Field(
            description="The tags (labels) that will be assigned to resources created by `dstack`"
        ),
    ] = None


class NebiusBackendConfigWithCreds(NebiusBackendConfig):
    """
    Same as `NebiusBackendConfig` but also includes creds.
    """

    creds: Annotated[AnyNebiusCreds, Field(description="The credentials")]


class NebiusBackendFileConfigWithCreds(NebiusBackendConfig):
    creds: AnyNebiusFileCreds = Field(description="The credentials")


AnyNebiusBackendConfig = Union[NebiusBackendConfig, NebiusBackendConfigWithCreds]


class NebiusStoredConfig(NebiusBackendConfig):
    """
    The backend config used for config parameters in the DB.
    Can extend `NebiusBackendConfig` with additional parameters.
    """

    pass


class NebiusConfig(NebiusStoredConfig):
    """
    The backend config used by `NebiusBackend` and `NebiusCompute`.
    """

    creds: AnyNebiusCreds


class NebiusOfferBackendData(CoreModel):
    fabrics: set[str] = set()
