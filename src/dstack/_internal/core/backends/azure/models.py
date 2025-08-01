from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class AzureClientCreds(CoreModel):
    type: Annotated[Literal["client"], Field(description="The type of credentials")] = "client"
    client_id: Annotated[str, Field(description="The client ID")]
    client_secret: Annotated[str, Field(description="The client secret")]
    # if tenant_id is missing, it will be populated from config info
    tenant_id: Optional[str]


class AzureDefaultCreds(CoreModel):
    type: Annotated[Literal["default"], Field(description="The type of credentials")] = "default"


AnyAzureCreds = Union[AzureClientCreds, AzureDefaultCreds]


class AzureCreds(CoreModel):
    __root__: AnyAzureCreds = Field(..., discriminator="type")


class AzureBackendConfig(CoreModel):
    type: Annotated[Literal["azure"], Field(description="The type of the backend")] = "azure"
    tenant_id: Annotated[str, Field(description="The tenant ID")]
    subscription_id: Annotated[str, Field(description="The subscription ID")]
    resource_group: Annotated[
        Optional[str],
        Field(
            description=(
                "The resource group for resources created by `dstack`."
                " If not specified, `dstack` will create a new resource group"
            )
        ),
    ] = None
    regions: Annotated[
        Optional[List[str]],
        Field(description="The list of Azure regions (locations). Omit to use all regions"),
    ] = None
    vpc_ids: Annotated[
        Optional[Dict[str, str]],
        Field(
            description=(
                "The mapping from configured Azure locations to network IDs."
                " A network ID must have a format `networkResourceGroup/networkName`"
                " If not specified, `dstack` will create a new network for every configured region"
            )
        ),
    ] = None
    public_ips: Annotated[
        Optional[bool],
        Field(
            description=(
                "A flag to enable/disable public IP assigning on instances."
                " `public_ips: false` requires `vpc_ids` that specifies custom networks with outbound internet connectivity"
                " provided by NAT Gateway or other mechanism."
                " Defaults to `true`"
            )
        ),
    ] = None
    vm_managed_identity: Annotated[
        Optional[str],
        Field(
            description=(
                "The managed identity to associate with provisioned VMs."
                " Must have a format `managedIdentityResourceGroup/managedIdentityName`"
            )
        ),
    ] = None
    tags: Annotated[
        Optional[Dict[str, str]],
        Field(description="The tags that will be assigned to resources created by `dstack`"),
    ] = None


class AzureBackendConfigWithCreds(AzureBackendConfig):
    creds: AnyAzureCreds = Field(..., description="The credentials", discriminator="type")


AnyAzureBackendConfig = Union[AzureBackendConfig, AzureBackendConfigWithCreds]


class AzureStoredConfig(AzureBackendConfig):
    resource_group: str = ""


class AzureConfig(AzureStoredConfig):
    creds: AnyAzureCreds

    @property
    def allocate_public_ips(self) -> bool:
        if self.public_ips is not None:
            return self.public_ips
        return True
