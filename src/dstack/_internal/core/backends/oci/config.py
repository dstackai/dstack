from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.oci import AnyOCICreds, OCIStoredConfig


class OCIConfig(OCIStoredConfig, BackendConfig):
    creds: AnyOCICreds
