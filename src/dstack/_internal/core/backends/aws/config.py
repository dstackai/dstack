from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.aws import AnyAWSCreds, AWSStoredConfig


class AWSConfig(AWSStoredConfig, BackendConfig):
    creds: AnyAWSCreds
