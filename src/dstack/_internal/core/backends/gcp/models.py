from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import Field, root_validator

from dstack._internal.core.backends.base.models import fill_data
from dstack._internal.core.models.common import CoreModel


class GCPServiceAccountCreds(CoreModel):
    type: Annotated[Literal["service_account"], Field(description="The type of credentials")] = (
        "service_account"
    )
    filename: Annotated[
        Optional[str], Field(description="The path to the service account file")
    ] = ""
    data: Annotated[str, Field(description="The contents of the service account file")]


class GCPDefaultCreds(CoreModel):
    type: Literal["default"] = "default"


AnyGCPCreds = Union[GCPServiceAccountCreds, GCPDefaultCreds]


class GCPCreds(CoreModel):
    __root__: AnyGCPCreds = Field(..., discriminator="type")


class GCPBackendConfig(CoreModel):
    type: Annotated[Literal["gcp"], Field(description="The type of backend")] = "gcp"
    project_id: Annotated[str, Field(description="The project ID")]
    regions: Annotated[
        Optional[List[str]], Field(description="The list of GCP regions. Omit to use all regions")
    ] = None
    vpc_name: Annotated[
        Optional[str],
        Field(description="The name of a custom VPC. If not specified, the default VPC is used"),
    ] = None
    extra_vpcs: Annotated[
        Optional[List[str]],
        Field(
            description=(
                "The names of additional VPCs used for GPUDirect. Specify eight VPCs to maximize bandwidth."
                " Each VPC must have a subnet and a firewall rule allowing internal traffic across all subnets"
            )
        ),
    ] = None
    vpc_project_id: Annotated[
        Optional[str],
        Field(description="The shared VPC hosted project ID. Required for shared VPC only"),
    ] = None
    public_ips: Annotated[
        Optional[bool],
        Field(
            description="A flag to enable/disable public IP assigning on instances. Defaults to `true`"
        ),
    ] = None
    nat_check: Annotated[
        Optional[bool],
        Field(
            description=(
                "A flag to enable/disable a check that Cloud NAT is configured for the VPC."
                " This should be set to `false` when `public_ips: false` and outbound internet connectivity"
                " is provided by a mechanism other than Cloud NAT such as a third-party NAT appliance."
                " Defaults to `true`"
            )
        ),
    ] = None
    vm_service_account: Annotated[
        Optional[str], Field(description="The service account to associate with provisioned VMs")
    ] = None
    tags: Annotated[
        Optional[Dict[str, str]],
        Field(
            description="The tags (labels) that will be assigned to resources created by `dstack`"
        ),
    ] = None


class GCPBackendConfigWithCreds(GCPBackendConfig):
    creds: AnyGCPCreds = Field(..., description="The credentials", discriminator="type")


class GCPServiceAccountFileCreds(CoreModel):
    type: Annotated[Literal["service_account"], Field(description="The type of credentials")] = (
        "service_account"
    )
    filename: Annotated[str, Field(description="The path to the service account file")]
    data: Annotated[
        Optional[str],
        Field(
            description=(
                "The contents of the service account file."
                " When configuring via `server/config.yml`, it's automatically filled from `filename`."
                " When configuring via UI, it has to be specified explicitly"
            )
        ),
    ] = None

    @root_validator
    def fill_data(cls, values):
        return fill_data(values)


AnyGCPFileCreds = Union[GCPServiceAccountFileCreds, GCPDefaultCreds]


class GCPBackendFileConfigWithCreds(GCPBackendConfig):
    creds: AnyGCPFileCreds = Field(..., description="The credentials", discriminator="type")


AnyGCPBackendConfig = Union[GCPBackendConfig, GCPBackendConfigWithCreds]


class GCPStoredConfig(GCPBackendConfig):
    pass


class GCPConfig(GCPStoredConfig):
    creds: AnyGCPCreds

    @property
    def allocate_public_ips(self) -> bool:
        if self.public_ips is not None:
            return self.public_ips
        return True

    @property
    def vpc_resource_name(self) -> str:
        vpc_name = self.vpc_name
        if vpc_name is None:
            vpc_name = "default"
        project_id = self.project_id
        if self.vpc_project_id is not None:
            project_id = self.vpc_project_id
        return f"projects/{project_id}/global/networks/{vpc_name}"
