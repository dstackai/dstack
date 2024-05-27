from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.aws import AnyAWSCreds, AWSStoredConfig


class AWSConfig(AWSStoredConfig, BackendConfig):
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
