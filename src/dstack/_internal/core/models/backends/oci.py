from pathlib import Path

from pydantic import Field
from typing_extensions import Annotated, List, Literal, Optional, Union

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class OCIConfigInfo(CoreModel):
    type: Literal["oci"] = "oci"
    regions: Optional[List[str]] = None


class OCIClientCreds(CoreModel):
    type: Annotated[Literal["client"], Field(description="The type of credentials")] = "client"
    user: Annotated[str, Field(description="User OCID")]
    tenancy: Annotated[str, Field(description="Tenancy OCID")]
    key_file: Annotated[Path, Field(description="Path to the PEM key")]
    fingerprint: Annotated[str, Field(description="Key fingerprint")]
    region: Annotated[
        str, Field(description="Name or key of any region the tenancy is subscribed to")
    ]


class OCIDefaultCreds(CoreModel):
    type: Annotated[Literal["default"], Field(description="The type of credentials")] = "default"


AnyOCICreds = Union[OCIClientCreds, OCIDefaultCreds]


class OCICreds(CoreModel):
    __root__: AnyOCICreds = Field(..., discriminator="type")


class OCIConfigInfoWithCreds(OCIConfigInfo):
    creds: AnyOCICreds


AnyOCIConfigInfo = Union[OCIConfigInfo, OCIConfigInfoWithCreds]


class OCIConfigInfoWithCredsPartial(CoreModel):
    type: Literal["oci"] = "oci"
    creds: Optional[AnyOCICreds]
    regions: Optional[List[str]]


class OCIConfigValues(CoreModel):
    type: Literal["oci"] = "oci"
    default_creds: bool = False
    regions: Optional[ConfigMultiElement]


class OCIStoredConfig(OCIConfigInfo):
    pass
