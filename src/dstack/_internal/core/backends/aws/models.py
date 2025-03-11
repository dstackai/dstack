from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class AWSOSImage(CoreModel):
    name: Annotated[str, Field(description="The AMI name")]
    owner: Annotated[
        str,
        Field(regex=r"^(\d{12}|self)$", description="The AMI owner, account ID or `self`"),
    ] = "self"
    user: Annotated[str, Field(description="The OS user for provisioning")]


class AWSOSImageConfig(CoreModel):
    cpu: Annotated[Optional[AWSOSImage], Field(description="The AMI used for CPU instances")] = (
        None
    )
    nvidia: Annotated[
        Optional[AWSOSImage], Field(description="The AMI used for NVIDIA GPU instances")
    ] = None


class AWSAccessKeyCreds(CoreModel):
    type: Annotated[Literal["access_key"], Field(description="The type of credentials")] = (
        "access_key"
    )
    access_key: Annotated[str, Field(description="The access key")]
    secret_key: Annotated[str, Field(description="The secret key")]


class AWSDefaultCreds(CoreModel):
    type: Annotated[Literal["default"], Field(description="The type of credentials")] = "default"


AnyAWSCreds = Union[AWSAccessKeyCreds, AWSDefaultCreds]


class AWSCreds(CoreModel):
    __root__: AnyAWSCreds = Field(..., discriminator="type")


class AWSBackendConfig(CoreModel):
    type: Annotated[Literal["aws"], Field(description="The type of the backend")] = "aws"
    regions: Annotated[
        Optional[List[str]], Field(description="The list of AWS regions. Omit to use all regions")
    ] = None
    vpc_name: Annotated[
        Optional[str],
        Field(
            description=(
                "The name of custom VPCs. All configured regions must have a VPC with this name."
                " If your custom VPCs don't have names or have different names in different regions, use `vpc_ids` instead."
            )
        ),
    ] = None
    vpc_ids: Annotated[
        Optional[Dict[str, str]],
        Field(
            description=(
                "The mapping from AWS regions to VPC IDs."
                " If `default_vpcs: true`, omitted regions will use default VPCs"
            )
        ),
    ] = None
    default_vpcs: Annotated[
        Optional[bool],
        Field(
            description=(
                "A flag to enable/disable using default VPCs in regions not configured by `vpc_ids`."
                " Set to `false` if default VPCs should never be used."
                " Defaults to `true`"
            )
        ),
    ] = None
    public_ips: Annotated[
        Optional[bool],
        Field(
            description=(
                "A flag to enable/disable public IP assigning on instances."
                " `public_ips: false` requires at least one private subnet with outbound internet connectivity"
                " provided by a NAT Gateway or a Transit Gateway."
                " Defaults to `true`"
            )
        ),
    ] = None
    iam_instance_profile: Annotated[
        Optional[str],
        Field(
            description=(
                "The name of the IAM instance profile to associate with EC2 instances."
                " You can also specify the IAM role name for roles created via the AWS console."
                " AWS automatically creates an instance profile and gives it the same name as the role"
            )
        ),
    ] = None
    tags: Annotated[
        Optional[Dict[str, str]],
        Field(description="The tags that will be assigned to resources created by `dstack`"),
    ] = None
    os_images: Annotated[
        Optional[AWSOSImageConfig],
        Field(
            description="The mapping of instance categories (CPU, NVIDIA GPU) to AMI configurations"
        ),
    ] = None


class AWSBackendConfigWithCreds(AWSBackendConfig):
    creds: AnyAWSCreds = Field(..., description="The credentials", discriminator="type")


AnyAWSBackendConfig = Union[AWSBackendConfig, AWSBackendConfigWithCreds]


class AWSStoredConfig(AWSBackendConfig):
    pass


class AWSConfig(AWSStoredConfig):
    creds: AnyAWSCreds

    @property
    def allocate_public_ips(self) -> bool:
        if self.public_ips is not None:
            return self.public_ips
        return True

    @property
    def use_default_vpcs(self) -> bool:
        if self.default_vpcs is not None:
            return self.default_vpcs
        return True
