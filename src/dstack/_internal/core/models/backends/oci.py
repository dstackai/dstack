from typing import Dict

from pydantic import Field, root_validator
from typing_extensions import Annotated, List, Literal, Optional, Union

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class OCIConfigInfo(CoreModel):
    type: Literal["oci"] = "oci"
    regions: Optional[List[str]] = None
    compartment_id: Optional[str] = None


class OCIClientCreds(CoreModel):
    type: Annotated[Literal["client"], Field(description="The type of credentials")] = "client"
    user: Annotated[str, Field(description="User OCID")]
    tenancy: Annotated[str, Field(description="Tenancy OCID")]
    key_file: Annotated[
        Optional[str],
        Field(
            description="Path to the user's private PEM key. Either this or `key_content` should be set"
        ),
    ]
    key_content: Annotated[
        Optional[str],
        Field(
            description="Content of the user's private PEM key. Either this or `key_file` should be set"
        ),
    ]
    pass_phrase: Annotated[
        Optional[str], Field(description="Passphrase for the private PEM key if it is encrypted")
    ]
    fingerprint: Annotated[str, Field(description="User's public key fingerprint")]
    region: Annotated[
        str, Field(description="Name or key of any region the tenancy is subscribed to")
    ]

    @root_validator
    def key_file_xor_key_content(cls, values):
        key_file, key_content = values["key_file"], values["key_content"]
        if key_file and key_content:
            raise ValueError("key_file and key_content are mutually exclusive")
        if not key_file and not key_content:
            raise ValueError("Either key_file or key_content should be set")
        return values


class OCIDefaultCreds(CoreModel):
    type: Annotated[Literal["default"], Field(description="The type of credentials")] = "default"
    file: Annotated[str, Field(description="Path to the OCI CLI-compatible config file")] = (
        "~/.oci/config"
    )
    profile: Annotated[str, Field(description="Profile to load from the config file")] = "DEFAULT"


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
    compartment_id: Optional[str]


class OCIConfigValues(CoreModel):
    type: Literal["oci"] = "oci"
    default_creds: bool = False
    regions: Optional[ConfigMultiElement]
    compartment_id: Optional[str] = None


class OCIStoredConfig(OCIConfigInfo):
    compartment_id: str
    subnet_ids_per_region: Dict[str, str]
